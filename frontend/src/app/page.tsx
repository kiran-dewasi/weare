"use client";

import { useState, useEffect } from "react";
import MagicInput from "@/components/MagicInput";
import DashboardStats from "@/components/DashboardStats";
import AuditReport from "@/components/AuditReport";
import { BarChart3, Shield, TrendingUp, ShoppingCart, Wallet, Scale, TrendingDown, FileText } from "lucide-react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API_CONFIG } from "@/lib/api-config";

export default function Dashboard() {
  const [bills, setBills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("overview");

  useEffect(() => {
    fetch(`${API_CONFIG.BASE_URL}/bills/receivables`, {
      headers: API_CONFIG.getHeaders()
    })
      .then(res => res.json())
      .then(data => {
        setBills(data);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, []);

  const [isSyncing, setIsSyncing] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);

  const handleSync = async () => {
    setIsSyncing(true);
    try {
      const res = await fetch(`${API_CONFIG.BASE_URL}/sync`, {
        method: "POST",
        headers: API_CONFIG.getHeaders()
      });
      if (res.ok) {
        setShowSuccess(true);
        setTimeout(() => {
          setShowSuccess(false);
          window.location.reload();
        }, 2000);
      } else {
        alert("Sync failed");
      }
    } catch (error) {
      alert("Sync error");
    } finally {
      setIsSyncing(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50 via-white to-blue-50">
      {/* Success Notification */}
      {showSuccess && (
        <div className="fixed top-20 right-4 z-50 bg-green-500 text-white px-6 py-3 rounded-lg shadow-lg flex items-center gap-2 animate-in slide-in-from-top">
          <span className="text-xl">✅</span>
          <span className="font-medium">Sync Completed Successfully!</span>
        </div>
      )}

      {/* Header with Sync Button */}
      <header className="border-b bg-white/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold bg-gradient-to-r from-purple-600 to-blue-600 bg-clip-text text-transparent">
                K24 Intelligence
              </h1>
              <p className="text-sm text-muted-foreground">Headless ERP for Tally</p>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full font-medium">
                ● Tally Live
              </span>
              <button
                onClick={handleSync}
                disabled={isSyncing}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 transition-colors text-sm font-medium"
              >
                {isSyncing ? "Syncing..." : "Sync Now"}
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        {/* AI Input */}
        <MagicInput />

        {/* Tabs */}
        <div className="w-full">
          <div className="flex gap-2 mb-6 border-b">
            <button
              onClick={() => setActiveTab("overview")}
              className={`flex items-center gap-2 px-4 py-2 border-b-2 transition-colors ${activeTab === "overview"
                ? "border-purple-600 text-purple-600"
                : "border-transparent text-gray-600 hover:text-gray-900"
                }`}
            >
              <BarChart3 className="h-4 w-4" />
              Overview
            </button>
            <button
              onClick={() => setActiveTab("reports")}
              className={`flex items-center gap-2 px-4 py-2 border-b-2 transition-colors ${activeTab === "reports"
                ? "border-purple-600 text-purple-600"
                : "border-transparent text-gray-600 hover:text-gray-900"
                }`}
            >
              <FileText className="h-4 w-4" />
              Reports
            </button>
            <button
              onClick={() => setActiveTab("operations")}
              className={`flex items-center gap-2 px-4 py-2 border-b-2 transition-colors ${activeTab === "operations"
                ? "border-purple-600 text-purple-600"
                : "border-transparent text-gray-600 hover:text-gray-900"
                }`}
            >
              <TrendingUp className="h-4 w-4" />
              Operations
            </button>
            <button
              onClick={() => setActiveTab("compliance")}
              className={`flex items-center gap-2 px-4 py-2 border-b-2 transition-colors ${activeTab === "compliance"
                ? "border-purple-600 text-purple-600"
                : "border-transparent text-gray-600 hover:text-gray-900"
                }`}
            >
              <Shield className="h-4 w-4" />
              Compliance
            </button>
          </div>

          {activeTab === "overview" && (
            <div className="space-y-8">
              {/* KPI Cards */}
              <DashboardStats />

              {/* Receivables Table */}
              <div className="bg-white rounded-xl shadow-sm border p-6">
                <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
                  <span className="text-2xl">💰</span> Outstanding Receivables
                </h2>
                {loading ? (
                  <div className="text-center py-8 text-muted-foreground">Loading...</div>
                ) : bills.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">No receivables found</div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left py-2 px-4 font-medium text-muted-foreground">Bill Ref</th>
                          <th className="text-left py-2 px-4 font-medium text-muted-foreground">Party</th>
                          <th className="text-right py-2 px-4 font-medium text-muted-foreground">Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        {bills.map((bill: any, idx: number) => (
                          <tr key={idx} className="border-b hover:bg-gray-50 transition-colors">
                            <td className="py-3 px-4">{bill.bill_name}</td>
                            <td className="py-3 px-4">{bill.party_name}</td>
                            <td className="py-3 px-4 text-right font-semibold text-green-600">
                              ₹{bill.amount?.toLocaleString('en-IN')}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === "reports" && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Sales Register */}
              <Link href="/reports/sales">
                <Card className="hover:shadow-md transition-shadow cursor-pointer border-l-4 border-l-blue-500">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                      <TrendingUp className="h-4 w-4 text-blue-500" />
                      Sales Register
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-gray-500">Monthly sales breakdown and analysis.</p>
                  </CardContent>
                </Card>
              </Link>

              {/* Purchase Register */}
              <Link href="/reports/purchase">
                <Card className="hover:shadow-md transition-shadow cursor-pointer border-l-4 border-l-orange-500">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                      <ShoppingCart className="h-4 w-4 text-orange-500" />
                      Purchase Register
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-gray-500">Expense tracking and vendor bills.</p>
                  </CardContent>
                </Card>
              </Link>

              {/* Cash Book */}
              <Link href="/reports/cash-book">
                <Card className="hover:shadow-md transition-shadow cursor-pointer border-l-4 border-l-green-500">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                      <Wallet className="h-4 w-4 text-green-500" />
                      Cash Book
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-gray-500">Cash-in-hand and daily transactions.</p>
                  </CardContent>
                </Card>
              </Link>

              {/* Balance Sheet */}
              <Link href="/reports/balance-sheet">
                <Card className="hover:shadow-md transition-shadow cursor-pointer border-l-4 border-l-purple-500">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                      <Scale className="h-4 w-4 text-purple-500" />
                      Balance Sheet
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-gray-500">Assets, Liabilities, and Capital.</p>
                  </CardContent>
                </Card>
              </Link>

              {/* Profit & Loss */}
              <Link href="/reports/profit-loss">
                <Card className="hover:shadow-md transition-shadow cursor-pointer border-l-4 border-l-red-500">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                      <TrendingDown className="h-4 w-4 text-red-500" />
                      Profit & Loss
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-gray-500">Income, Expenses, and Net Profit.</p>
                  </CardContent>
                </Card>
              </Link>

              {/* GST Summary */}
              <Link href="/reports/gst">
                <Card className="hover:shadow-md transition-shadow cursor-pointer border-l-4 border-l-indigo-500">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                      <FileText className="h-4 w-4 text-indigo-500" />
                      GST Summary
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-gray-500">GSTR-1 vs GSTR-3B Analysis.</p>
                  </CardContent>
                </Card>
              </Link>
            </div>
          )}

          {activeTab === "operations" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Receipt */}
              <Link href="/operations/receipt">
                <Card className="hover:shadow-md transition-shadow cursor-pointer border-l-4 border-l-green-600">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                      <TrendingUp className="h-4 w-4 text-green-600" />
                      Create Receipt
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-gray-500">Record money received from customers.</p>
                  </CardContent>
                </Card>
              </Link>

              {/* Payment */}
              <Link href="/operations/payment">
                <Card className="hover:shadow-md transition-shadow cursor-pointer border-l-4 border-l-orange-600">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                      <TrendingDown className="h-4 w-4 text-orange-600" />
                      Create Payment
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-gray-500">Record payments made to vendors.</p>
                  </CardContent>
                </Card>
              </Link>
            </div>
          )}

          {activeTab === "compliance" && (
            <AuditReport />
          )}
        </div>
      </main>
    </div>
  );
}
