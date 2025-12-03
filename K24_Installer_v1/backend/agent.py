from langchain_google_genai import ChatGoogleGenerativeAI
import pandas as pd
from typing import Union, Dict, Any
import os
from backend.tally_connector import TallyConnector, get_customer_details
from backend.tally_live_update import create_voucher_in_tally, TallyAPIError, TallyIgnoredError
from backend.tally_xml_builder import TallyXMLValidationError
from dotenv import load_dotenv
load_dotenv()

class TallyAgent:
    """Agentic AI for Tally ledger data: understands intent and performs actions."""

    def __init__(self, model_name: str = None, api_key: str = None):
        """Initialize the TallyAgent with a configurable Gemini model.
        The model can be provided directly, or via the GEMINI_MODEL env var.
        Defaults to 'gemini-2.5-flash' if neither is provided.
        """
        # Resolve model name: parameter > env > default
        if model_name is None:
            model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        # Get API key from parameter or environment variable
        if api_key is None:
            api_key = os.getenv("GOOGLE_API_KEY")
            if api_key is None:
                raise ValueError("API key must be provided either as parameter or GOOGLE_API_KEY environment variable")

        self.llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key)

    def parse_intent(self, command: str) -> Dict[str, Any]:
        """
        Uses LLM to parse user command into structured intent and parameters.
        Expects output in Python dict format only.
        """
        prompt = (
            "You are a Tally business assistant. Read the user's command below and reply ONLY as a valid Python dictionary (no explanation, no prose).\n"
            "Your output must look like this (examples):\n"
            "{'intent': 'update', 'params': {'entry_id': 103, 'updates': {'Amount': 21000}}}\n"
            "{'intent': 'add', 'params': {'entry': {'ID': 140, 'Amount': 5500, 'Account': 'Sales'}}}\n"
            "{'intent': 'delete', 'params': {'entry_id': 140}}\n"
            "{'intent': 'audit', 'params': {}}\n"
            "Available intents: ['audit', 'update', 'add', 'delete', 'summarize']\n"
            "User command: " + command + "\n"
            "Reply ONLY as a Python dictionary. Do not add any text, explanation, or formatting outside the dict."
        )
        intent_msg = self.llm.invoke(prompt)
        intent_out = getattr(intent_msg, "content", str(intent_msg))
        print("Intent Chain Output:", intent_out)
        # Safely parse output as Python dict:
        try:
            import ast
            parsed_dict = ast.literal_eval(intent_out.strip())
            intent = parsed_dict.get("intent", "audit")
            params = parsed_dict.get("params", {})
        except Exception as e:
            print("Failed to parse intent output:", e)
            intent = "audit"
            params = {}
        return {
            "raw_output": intent_out,
            "intent": intent,
            "params": params
        }

    def analyze_with_pandas(self, df: pd.DataFrame, query: str) -> str:
        """
        Generates and executes Pandas code to answer complex queries.
        This allows for temporal analysis ("last month vs this month") and aggregations
        that are impossible with simple context stuffing.
        """
        if df is None or df.empty:
            return "No data available to analyze."

        # 1. Generate Code
        prompt = (
            "You are a Python Data Analyst. You have a pandas DataFrame named `df` containing Tally accounting data.\n"
            f"DataFrame Columns: {list(df.columns)}\n"
            "Sample Data:\n"
            f"{df.head(3).to_string()}\n\n"
            f"User Query: \"{query}\"\n\n"
            "Write Python code to answer this query.\n"
            "- The code must assign the final answer to a variable named `result`.\n"
            "- Use `df` variable directly.\n"
            "- If the query involves dates, ensure you convert the 'Date' or 'DATE' column to datetime first using pd.to_datetime().\n"
            "- Return ONLY valid Python code. No markdown, no explanations, no ```python blocks.\n"
        )
        
        try:
            msg = self.llm.invoke(prompt)
            code = getattr(msg, "content", str(msg)).strip()
            
            # Clean code (remove markdown if present)
            if code.startswith("```"):
                code = code.split("\n", 1)[1]
                if code.endswith("```"):
                    code = code.rsplit("\n", 1)[0]
            
            print(f"[AGENT] Generated Code:\n{code}")
            
            # 2. Execute Code
            local_vars = {"df": df, "pd": pd}
            exec(code, {}, local_vars)
            
            # 3. Get Result
            result = local_vars.get("result", "No result variable found.")
            return str(result)
            
        except Exception as e:
            print(f"[AGENT] Analysis failed: {e}")
            return f"I tried to analyze the data but encountered an error: {str(e)}"

    # RAG audit method (same as previous)
    def audit(self, df: pd.DataFrame, question: str) -> str:
        # For simple questions or if dataframe is small, use old method
        # For complex queries, use new pandas method
        if len(df) > 50 or any(k in question.lower() for k in ["total", "sum", "count", "average", "compare", "month", "year", "vs"]):
            return self.analyze_with_pandas(df, question)

        data_str = df.head(50).to_string(index=False)
        audit_prompt = (
            "You are a financial audit AI for Tally data.\n"
            f"Ledger:\n{data_str}\n"
            f"Audit instruction:\n{question}\n"
            "Provide a structured response in markdown format with the following sections:\n"
            "### 📊 Summary\n"
            "### 🔍 Key Findings\n"
            "### ⚠️ Anomalies\n"
            "### 💡 Recommendations\n"
            "Keep it concise and professional."
        )
        msg = self.llm.invoke(audit_prompt)
        return getattr(msg, "content", str(msg))

    def act(self, ledger_crud, command: str) -> Union[str, dict]:
        parsed = self.parse_intent(command)
        # Try to use the intent value from LLM output. Fallback to "audit"
        intent = parsed.get("intent", "audit")
        params = parsed.get("params")
        raw = parsed.get("raw_output", "")

        try:
            if intent == "audit":
                return self.audit(ledger_crud.df, command)
            elif intent == "update":
                entry_id = params.get("entry_id")
                updates = params.get("updates")
                if entry_id is None or not updates:
                    raise ValueError("Could not extract entry_id or updates from command.")
                ledger_crud.update_entry(entry_id, updates)
                return {"status": f"Updated entry {entry_id}.", "updates": updates}
            elif intent == "add":
                entry = params.get("entry")
                if not entry:
                    raise ValueError("No entry data found in command.")
                ledger_crud.add_entry(entry)
                return {"status": "Added new entry.", "entry": entry}
            elif intent == "delete":
                entry_id = params.get("entry_id")
                if entry_id is None:
                    raise ValueError("No entry_id found for deletion.")
                ledger_crud.delete_entry(entry_id)
                return {"status": f"Deleted entry {entry_id}."}
            elif intent == "summarize":
                # Example placeholder
                return f"Summarize called with params: {params}"
            else:
                return {"error": f"Unknown intent. Raw output: {raw}"}
        except Exception as e:
            return {"error": str(e), "raw": raw}

    def act_and_push_live(self, company_name: str, command: str, tally_url: str = "http://localhost:9000") -> dict:
        """
        Full agentic pipeline for a live Tally add/update:
        - Parse command for intent and details
        - Fetch ledgers
        - Lookup customer
        - Enrich parameters
        - Build Voucher XML
        - Push to Tally
        Always logs steps. Falls back to legacy .act() if Tally fails.
        """
        # 1. Parse intent
        parsed = self.parse_intent(command)
        intent = parsed.get("intent")
        params = parsed.get("params", {})
        party = params.get("party_ledger") or params.get("party") or params.get("Party")
        amount = params.get("amount") or params.get("Amount")
        voucher_type = params.get("voucher_type", "Payment")
        date = params.get("date") or pd.Timestamp.now().strftime("%Y%m%d")
        narration = params.get("narration", "")
        voucher_number = params.get("voucher_number")
        print(f"[LOG] Parsed agent command. Intent: {intent}, Params: {params}")

        # 2. Fetch ledgers from live Tally
        try:
            tc = TallyConnector(tally_url)
            ledgers_df = tc.fetch_ledgers_full(company_name)
            print(f"[LOG] Fetched ledgers ({len(ledgers_df)}) from Tally.")
        except Exception as ex:
            print(f"[ERROR] Could not fetch live ledgers: {ex}. Falling back to legacy mode.")
            return self.act(None, command)

        # 3. Lookup customer details
        customer_details = get_customer_details(ledgers_df, party) if party else {}
        if not customer_details:
            print(f"[WARN] No details found for '{party}'; continuing with base params.")

        # 4. Enrich parameters
        enriched_params = {**params, **customer_details}

        # 5. Build voucher XML using strict schema builder
        try:
            amount_value = float(amount)
        except (TypeError, ValueError) as ex:
            print(f"[ERROR] Invalid amount '{amount}': {ex}")
            return {"error": "Invalid amount supplied", "details": str(ex)}

        voucher_fields = {
            "DATE": str(date),
            "VOUCHERTYPENAME": str(voucher_type),
            "PARTYLEDGERNAME": str(party) if party else "",
            "NARRATION": str(narration or ""),
        }
        if voucher_number:
            voucher_fields["VOUCHERNUMBER"] = str(voucher_number)

        line_items = [
            {
                "ledger_name": str(party) if party else "",
                "amount": amount_value,
                "is_deemed_positive": amount_value < 0,
            }
        ]

        try:
            response = create_voucher_in_tally(
                company_name=company_name,
                voucher_fields=voucher_fields,
                line_items=line_items,
                tally_url=tally_url,
            )
            print(f"[LOG] Push response: {response.to_dict()}")
            return {
                "status": "pushed_to_tally",
                "intent": intent,
                "party": party,
                "amount": amount,
                "response": response.to_dict(),
            }
        except (TallyXMLValidationError, TallyAPIError, TallyIgnoredError) as ex:
            print(f"[ERROR] Failed to build XML: {ex}")
            return {
                "error": "Failed to push voucher to Tally",
                "details": str(ex),
                "response": getattr(ex, "response", None).to_dict() if getattr(ex, "response", None) else None,
            }
        except Exception as ex:
            print(f"[ERROR] Failed to push to Tally: {ex}")
            return {"error": "Push to Tally failed", "details": str(ex)}


# Backward compatibility wrapper for existing api.py
class TallyAuditAgent:
    """Backward compatibility wrapper for TallyAgent."""
    
    def __init__(self, model_name: str = None, api_key: str = None):
        """Initialize with same model resolution as TallyAgent (defaults to gemini-2.5-flash)."""
        self.agent = TallyAgent(model_name=model_name, api_key=api_key)
    
    def ask_audit_question(self, df: pd.DataFrame, question: str) -> str:
        """
        Accept a Pandas dataframe and audit question, send to Gemini LLM, and return answer.
        """
        return self.agent.audit(df, question)


# Example usage
if __name__ == "__main__":
    # The following legacy CSV & CRUD tests are commented out to avoid file errors:
    # from backend.loader import LedgerLoader
    # from backend.crud import LedgerCRUD
    # df = LedgerLoader.load_csv("data/sample_ledger.csv")
    # if df is not None:
    #     ledger_crud = LedgerCRUD(df)
    #     agent = TallyAgent(model_name="gemini-pro", api_key=os.getenv("GOOGLE_API_KEY"))
    #     # Try an audit instruction
    #     out = agent.act(ledger_crud, "Audit this ledger for duplicate entries and large suspicious transactions.")
    #     print("Agent Output:", out)
    #     # Try a modify command
    #     out2 = agent.act(ledger_crud, "Update closing balance for Ledger ABC to 25000.")
    #     print("Agent Output:", out2)

    # Only run the live Tally pipeline demo:
    agent = TallyAgent(api_key=os.getenv("GOOGLE_API_KEY"))
    company = "SHREE JI SALES"
    cmd = "Add payment to Shree Ji Sales for \u20B95000"
    result = agent.act_and_push_live(company, cmd)
    print("[TEST] Final agent pipeline result:", result)
