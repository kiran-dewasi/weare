"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Plus, Receipt, CreditCard, ShoppingCart, PackageSearch, RefreshCw } from "lucide-react";
import MagicInput from "@/components/MagicInput";
import TransactionDetailModal from "@/components/TransactionDetailModal";

interface Voucher {
    date: string;
    voucher_type: string;
    voucher_number: string;
    party_name: string;
    amount: number;
    narration: string;
}

export default function DayBook() {
    const router = useRouter();
    const [vouchers, setVouchers] = useState<Voucher[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [filterType, setFilterType] = useState<string>("all");
    const [selectedVoucher, setSelectedVoucher] = useState<Voucher | null>(null);
    const [isModalOpen, setIsModalOpen] = useState(false);

    useEffect(() => {
        fetchVouchers();
    }, []);

    const fetchVouchers = async () => {
        setLoading(true);
        setError(null);

        try {
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 5000); // 5 second timeout

            const res = await fetch("http://127.0.0.1:8001/vouchers", {
                headers: { "x-api-key": "k24-secret-key-123" },
                signal: controller.signal
            });

            clearTimeout(timeout);

            if (!res.ok) {
                throw new Error(`Server error: ${res.status} ${res.statusText}`);
            }

            const data = await res.json();
            setVouchers(data.vouchers || []);
        } catch (err: any) {
            console.error("Failed to fetch vouchers", err);

            if (err.name === 'AbortError') {
                setError('Request timeout. Backend may be slow or not responding.');
            } else if (err.message.includes('Failed to fetch')) {
                setError('Cannot connect to backend. Please check if the server is running on port 8001.');
            } else {
                setError(`Failed to load vouchers: ${err.message}`);
            }
        } finally {
            setLoading(false);
        }
    };

    const filteredVouchers = filterType === "all"
        ? vouchers
        : vouchers.filter(v => v.voucher_type.toLowerCase() === filterType.toLowerCase());

    const voucherTypeCounts = {
        receipt: vouchers.filter(v => v.voucher_type === "Receipt").length,
        payment: vouchers.filter(v => v.voucher_type === "Payment").length,
        sales: vouchers.filter(v => v.voucher_type === "Sales").length,
        purchase: vouchers.filter(v => v.voucher_type === "Purchase").length
    };

    const getIcon = (type: string) => {
        switch (type.toLowerCase()) {
            case "receipt": return <Receipt className="h-4 w-4" />;
            case "payment": return <CreditCard className="h-4 w-4" />;
            case "sales": return <ShoppingCart className="h-4 w-4" />;
            case "purchase": return <PackageSearch className="h-4 w-4" />;
            default: return null;
        }
    };

    const getTypeColor = (type: string) => {
        switch (type.toLowerCase()) {
            case "receipt": return "text-green-600 bg-green-50";
            case "payment": return "text-red-600 bg-red-50";
            case "sales": return "text-blue-600 bg-blue-50";
            case "purchase": return "text-orange-600 bg-orange-50";
            default: return "text-gray-600 bg-gray-50";
        }
    };

    return (
        <div className="p-8 space-y-6 pb-24">
            {/* Header */}
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Day Book</h1>
                    <p className="text-muted-foreground">All transactions</p>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" size="icon" onClick={fetchVouchers} title="Refresh">
                        <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                    </Button>
                    <Button onClick={() => router.push("/vouchers/new/sales")} className="bg-blue-600 hover:bg-blue-700">
                        <ShoppingCart className="mr-2 h-4 w-4" />
                        New Invoice
                    </Button>
                    <Button onClick={() => router.push("/vouchers/new/receipt")} className="bg-green-600 hover:bg-green-700">
                        <Receipt className="mr-2 h-4 w-4" />
                        New Receipt
                    </Button>
                    <Button onClick={() => router.push("/vouchers/new/payment")} className="bg-red-600 hover:bg-red-700">
                        <CreditCard className="mr-2 h-4 w-4" />
                        New Payment
                    </Button>
                </div>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => setFilterType("receipt")}>
                    <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                        <CardTitle className="text-sm font-medium">Receipts</CardTitle>
                        <Receipt className="h-4 w-4 text-green-600" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{voucherTypeCounts.receipt}</div>
                    </CardContent>
                </Card>

                <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => setFilterType("payment")}>
                    <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                        <CardTitle className="text-sm font-medium">Payments</CardTitle>
                        <CreditCard className="h-4 w-4 text-red-600" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{voucherTypeCounts.payment}</div>
                    </CardContent>
                </Card>

                <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => setFilterType("sales")}>
                    <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                        <CardTitle className="text-sm font-medium">Sales</CardTitle>
                        <ShoppingCart className="h-4 w-4 text-blue-600" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{voucherTypeCounts.sales}</div>
                    </CardContent>
                </Card>

                <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => setFilterType("purchase")}>
                    <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                        <CardTitle className="text-sm font-medium">Purchases</CardTitle>
                        <PackageSearch className="h-4 w-4 text-orange-600" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{voucherTypeCounts.purchase}</div>
                    </CardContent>
                </Card>
            </div>

            {/* Filter */}
            {filterType !== "all" && (
                <div className="flex items-center gap-2">
                    <span className="text-sm text-muted-foreground">Showing: {filterType}</span>
                    <Button variant="ghost" size="sm" onClick={() => setFilterType("all")}>
                        Clear Filter
                    </Button>
                </div>
            )}

            {/* Vouchers List */}
            <Card>
                <CardHeader>
                    <CardTitle>Transactions</CardTitle>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <div className="text-center py-8">
                            <p className="text-muted-foreground">Loading vouchers...</p>
                        </div>
                    ) : error ? (
                        <div className="text-center py-8">
                            <p className="text-red-600 font-medium mb-2">{error}</p>
                            <p className="text-sm text-muted-foreground mb-4">Check the browser console (F12) for more details</p>
                            <Button onClick={fetchVouchers} variant="outline" size="sm">
                                Retry
                            </Button>
                        </div>
                    ) : filteredVouchers.length === 0 ? (
                        <p className="text-muted-foreground text-center py-8">No vouchers found.</p>
                    ) : (
                        <div className="space-y-3">
                            {filteredVouchers.map((v, idx) => (
                                <div
                                    key={idx}
                                    className="flex items-center justify-between p-4 border rounded-lg hover:bg-gray-50 transition-colors cursor-pointer"
                                    onClick={() => {
                                        setSelectedVoucher(v);
                                        setIsModalOpen(true);
                                    }}
                                >
                                    <div className="flex items-center gap-4 flex-1">
                                        <div className={`p-2 rounded-lg ${getTypeColor(v.voucher_type)}`}>
                                            {getIcon(v.voucher_type)}
                                        </div>
                                        <div className="flex-1">
                                            <div className="flex items-center gap-2">
                                                <p className="font-medium">{v.party_name || "N/A"}</p>
                                                <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
                                                    #{v.voucher_number || "—"}
                                                </span>
                                            </div>
                                            <p className="text-sm text-muted-foreground">{v.date}</p>
                                            {v.narration && (
                                                <p className="text-xs text-gray-500 italic mt-1">{v.narration}</p>
                                            )}
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <p className={`font-bold text-lg ${v.voucher_type === 'Receipt' || v.voucher_type === 'Sales'
                                            ? 'text-green-600'
                                            : 'text-red-600'
                                            }`}>
                                            {v.voucher_type === 'Receipt' || v.voucher_type === 'Sales' ? '+' : '-'}
                                            ₹{(v.amount || 0).toLocaleString('en-IN')}
                                        </p>
                                        <p className="text-xs text-muted-foreground">{v.voucher_type}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Context-Aware AI */}
            <div className="fixed bottom-6 right-6 w-96 z-50">
                <MagicInput
                    isFullPage={false}
                    allowEmbedded={true}
                    pageContext={{
                        page: "daybook",
                        voucher_count: vouchers.length,
                        receipt_count: voucherTypeCounts.receipt,
                        payment_count: voucherTypeCounts.payment
                    }}
                />
            </div>

            {/* Transaction Detail Modal */}
            <TransactionDetailModal
                isOpen={isModalOpen}
                onClose={() => {
                    setIsModalOpen(false);
                    setSelectedVoucher(null);
                }}
                voucher={selectedVoucher}
            />
        </div>
    );
}
