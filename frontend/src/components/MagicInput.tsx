"use client";

import { useState, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Sparkles, ArrowRight, Check, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { FollowUpCard, PartySelectorCard, ItemSelectorCard } from "@/components/chat/ChatCards";

interface DraftVoucher {
    party_name: string;
    voucher_type: string;
    amount: number;
    items: { name: string; quantity: number; rate: number; amount: number }[];
}

export default function MagicInput({ isFullPage = false, theme = "light" }: { isFullPage?: boolean, theme?: "light" | "dark" | "claude" }) {
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const [draft, setDraft] = useState<DraftVoucher | null>(null);
    const [response, setResponse] = useState<string | null>(null);
    const [followUp, setFollowUp] = useState<{ question: string; missing_slots: string[] } | null>(null);
    const [cardData, setCardData] = useState<any | null>(null);
    const router = useRouter();
    const searchParams = useSearchParams();

    const isDark = theme === "dark";
    const isClaude = theme === "claude";

    let baseInputClass = "pl-10 h-14 text-lg shadow-lg border-purple-200 focus-visible:ring-purple-500";
    let iconColor = "text-purple-500";
    let buttonClass = "absolute right-2 top-2 bottom-2 bg-purple-600 hover:bg-purple-700";

    if (isDark) {
        baseInputClass = "pl-12 h-16 text-xl bg-white/5 border-white/10 text-white placeholder:text-gray-500 focus-visible:ring-purple-500/50 focus-visible:border-purple-500/50 shadow-2xl backdrop-blur-xl";
        iconColor = "text-purple-400";
        buttonClass = "absolute right-3 top-3 bottom-3 bg-white text-black hover:bg-gray-200 rounded-lg px-4 transition-all";
    } else if (isClaude) {
        baseInputClass = "pl-4 h-[120px] text-lg bg-white border border-[#E6E1D6] text-[#282828] placeholder:text-[#888888] shadow-sm focus-visible:ring-2 focus-visible:ring-[#D96C46]/20 focus-visible:border-[#D96C46] rounded-2xl resize-none py-4 align-top";
        iconColor = "text-[#D96C46]";
        buttonClass = "absolute right-3 bottom-3 bg-[#D96C46] text-white hover:bg-[#C05A35] rounded-lg px-3 py-1.5 transition-all font-medium text-sm";
    } else {
        // Linear/Vercel Style (Light)
        baseInputClass = "pl-12 h-16 text-lg bg-white border border-gray-200 text-gray-900 placeholder:text-gray-400 shadow-sm focus-visible:ring-2 focus-visible:ring-gray-900 focus-visible:border-transparent rounded-xl transition-all";
        iconColor = "text-gray-400";
        buttonClass = "absolute right-3 top-3 bottom-3 bg-gray-900 text-white hover:bg-gray-800 rounded-lg px-4 transition-all shadow-sm";
    }

    // Auto-trigger if query param exists (only on full page)
    useEffect(() => {
        if (isFullPage) {
            const q = searchParams.get("q");
            if (q && !input && !draft) {
                setInput(q);
                // Small delay to ensure state is set before triggering
                setTimeout(() => handleMagic(q), 100);
            }
        }
    }, [isFullPage, searchParams]);

    const handleMagic = async (overrideInput?: string) => {
        const textToProcess = overrideInput || input;
        if (!textToProcess.trim()) return;

        // If on dashboard (not full page), redirect to chat page
        if (!isFullPage) {
            router.push(`/chat?q=${encodeURIComponent(textToProcess)}`);
            return;
        }

        setLoading(true);
        try {
            const res = await fetch("http://127.0.0.1:8001/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "x-api-key": "k24-secret-key-123"
                },
                body: JSON.stringify({ message: textToProcess, user_id: "k24_user" }),
            });
            const data = await res.json();

            // Handle different response types
            if (data.type === "draft_voucher") {
                setDraft(data.data);
                setResponse(null);
                setFollowUp(null);
                setCardData(null);
            } else if (data.type === "follow_up") {
                setFollowUp({
                    question: data.response,
                    missing_slots: data.missing_slots || []
                });
                setResponse(null);
                setDraft(null);
                setCardData(null);
            } else if (data.type === "card") {
                setCardData(data);
                setResponse(null);
                setDraft(null);
                setFollowUp(null);
            } else {
                // Text response
                setResponse(data.response || data.message);
                setDraft(null);
                setFollowUp(null);
                setCardData(null);
            }
        } catch (err) {
            console.error("Magic failed:", err);
            setResponse("⚠️ AI Brain is offline. Please check if the backend is running.");
        } finally {
            setLoading(false);
        }
    };

    const handleConfirm = async () => {
        if (!draft) return;

        try {
            const res = await fetch("http://127.0.0.1:8001/vouchers", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "x-api-key": "k24-secret-key-123"
                },
                body: JSON.stringify(draft),
            });
            const result = await res.json();

            if (res.ok) {
                alert(`Success! Voucher Created. \nRef: ${result.tally_response?.raw || "Synced"}`);
                setDraft(null);
                setInput("");
                // Trigger a refresh of the dashboard data
                window.location.reload();
            } else {
                alert(`Error: ${result.message}`);
            }
        } catch (err) {
            console.error("Save failed:", err);
            alert("Failed to connect to backend.");
        }
    };

    return (
        <div className="w-full max-w-2xl mx-auto mb-8">
            <div className="relative">
                {!isClaude && (
                    <div className={`absolute inset-y-0 left-4 flex items-center pointer-events-none ${isDark ? 'left-5' : 'left-3'}`}>
                        <Sparkles className={`h-5 w-5 ${iconColor} animate-pulse`} />
                    </div>
                )}

                {isClaude ? (
                    <textarea
                        placeholder="How can I help you with your business today?"
                        className={`${baseInputClass} w-full transition-all duration-300`}
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Enter" && !e.shiftKey) {
                                e.preventDefault();
                                handleMagic();
                            }
                        }}
                        disabled={loading}
                        suppressHydrationWarning
                    />
                ) : (
                    <Input
                        placeholder="✨ Describe your transaction..."
                        className={`${baseInputClass} transition-all duration-300`}
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && handleMagic()}
                        disabled={loading}
                    />
                )}

                <Button
                    className={buttonClass}
                    onClick={() => handleMagic()}
                    disabled={loading}
                >
                    {loading ? (
                        <span className="animate-pulse">...</span>
                    ) : (
                        isClaude ? "Send Message" : <ArrowRight className="h-5 w-5" />
                    )}
                </Button>
            </div>

            {/* Draft Confirmation Card */}
            {draft && (
                <Card className="mt-4 border-purple-200 shadow-xl animate-in fade-in slide-in-from-top-4">
                    <CardHeader className="bg-purple-50 pb-2">
                        <CardTitle className="text-purple-900 text-lg flex justify-between items-center">
                            <span>Confirm {draft.voucher_type}?</span>
                            <span className="text-sm font-normal text-purple-700 bg-purple-100 px-2 py-1 rounded-full">Draft</span>
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="text-xs text-muted-foreground uppercase font-bold">Party</label>
                                <div className="text-lg font-medium">{draft.party_name}</div>
                            </div>
                            <div className="text-right">
                                <label className="text-xs text-muted-foreground uppercase font-bold">Total Amount</label>
                                <div className="text-2xl font-bold text-green-600">₹{draft.amount.toLocaleString('en-IN')}</div>
                            </div>
                        </div>

                        <div className="mt-4">
                            <label className="text-xs text-muted-foreground uppercase font-bold">Items</label>
                            <ul className="mt-1 space-y-1">
                                {draft.items.map((item, idx) => (
                                    <li key={idx} className="flex justify-between text-sm border-b border-dashed pb-1">
                                        <span>{item.name} <span className="text-muted-foreground">x {item.quantity}</span></span>
                                        <span>₹{item.amount.toLocaleString('en-IN')}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </CardContent>
                    <CardFooter className="flex justify-end gap-2 bg-gray-50 pt-4">
                        <Button variant="ghost" onClick={() => setDraft(null)} className="text-red-600 hover:text-red-700 hover:bg-red-50">
                            <X className="mr-2 h-4 w-4" /> Cancel
                        </Button>
                        <Button onClick={handleConfirm} className="bg-green-600 hover:bg-green-700">
                            <Check className="mr-2 h-4 w-4" /> Save to Tally
                        </Button>
                    </CardFooter>
                </Card>
            )}

            {/* Follow-up Question Card */}
            {followUp && (
                <FollowUpCard
                    question={followUp.question}
                    missingSlots={followUp.missing_slots}
                    onResponse={(answer) => {
                        setFollowUp(null);
                        handleMagic(answer);
                    }}
                />
            )}

            {/* AI Response Card */}
            {response && (
                <Card className="mt-4 border-[#E6E1D6] shadow-lg animate-in fade-in slide-in-from-top-4">
                    <CardHeader className="bg-gradient-to-r from-[#F5F2EB] to-white pb-3">
                        <CardTitle className="text-[#1A1A1A] text-lg flex items-center gap-2">
                            <Sparkles className="h-5 w-5 text-[#D96C46]" />
                            <span>KITTU</span>
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <div className="prose prose-sm max-w-none text-[#282828]">
                            {response.split('\n').map((line, idx) => (
                                <p key={idx} className="mb-2">{line}</p>
                            ))}
                        </div>
                    </CardContent>
                    <CardFooter className="bg-gray-50 justify-end">
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setResponse(null)}
                            className="text-gray-600 hover:text-gray-900"
                        >
                            Clear
                        </Button>
                    </CardFooter>
                </Card>
            )}
        </div>
    );
}
