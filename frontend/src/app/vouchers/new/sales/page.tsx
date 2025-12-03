"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Plus, Trash2, Loader2 } from "lucide-react";

interface LineItem {
    id: string;
    description: string;
    quantity: number;
    rate: number;
    amount: number;
}

export default function NewSalesInvoice() {
    const router = useRouter();

    // Form State
    const [partyName, setPartyName] = useState("");
    const [invoiceNumber, setInvoiceNumber] = useState("");
    const [date, setDate] = useState(new Date().toISOString().split('T')[0]);
    const [lineItems, setLineItems] = useState<LineItem[]>([
        { id: "1", description: "", quantity: 1, rate: 0, amount: 0 }
    ]);
    const [gstRate, setGstRate] = useState(18); // Default 18% GST
    const [discount, setDiscount] = useState(0);
    const [narration, setNarration] = useState("");

    // UI State
    const [loading, setLoading] = useState(false);
    const [partySuggestions, setPartySuggestions] = useState<string[]>([]);
    const [showSuggestions, setShowSuggestions] = useState(false);

    // Calculations
    const subtotal = lineItems.reduce((sum, item) => sum + item.amount, 0);
    const discountAmount = (subtotal * discount) / 100;
    const taxableAmount = subtotal - discountAmount;
    const gstAmount = (taxableAmount * gstRate) / 100;
    const grandTotal = taxableAmount + gstAmount;

    // Fetch party suggestions
    useEffect(() => {
        if (partyName.length < 2) {
            setPartySuggestions([]);
            return;
        }

        const fetchSuggestions = async () => {
            try {
                const res = await fetch(`http://localhost:8001/ledgers/search?query=${encodeURIComponent(partyName)}`, {
                    headers: { "x-api-key": "k24-secret-key-123" }
                });
                const data = await res.json();
                setPartySuggestions(data.matches || []);
                setShowSuggestions(true);
            } catch (error) {
                console.error("Failed to fetch suggestions", error);
            }
        };

        const debounce = setTimeout(fetchSuggestions, 300);
        return () => clearTimeout(debounce);
    }, [partyName]);

    const addLineItem = () => {
        const newItem: LineItem = {
            id: Date.now().toString(),
            description: "",
            quantity: 1,
            rate: 0,
            amount: 0
        };
        setLineItems([...lineItems, newItem]);
    };

    const removeLineItem = (id: string) => {
        if (lineItems.length > 1) {
            setLineItems(lineItems.filter(item => item.id !== id));
        }
    };

    const updateLineItem = (id: string, field: keyof LineItem, value: any) => {
        setLineItems(lineItems.map(item => {
            if (item.id === id) {
                const updated = { ...item, [field]: value };
                // Recalculate amount
                if (field === 'quantity' || field === 'rate') {
                    updated.amount = updated.quantity * updated.rate;
                }
                return updated;
            }
            return item;
        }));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);

        try {
            const res = await fetch("http://localhost:8001/vouchers/sales", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "x-api-key": "k24-secret-key-123"
                },
                body: JSON.stringify({
                    party_name: partyName,
                    invoice_number: invoiceNumber,
                    date,
                    items: lineItems.map(item => ({
                        description: item.description,
                        quantity: item.quantity,
                        rate: item.rate,
                        amount: item.amount
                    })),
                    subtotal,
                    discount_percent: discount,
                    discount_amount: discountAmount,
                    gst_rate: gstRate,
                    gst_amount: gstAmount,
                    grand_total: grandTotal,
                    narration
                })
            });

            const data = await res.json();

            if (res.ok) {
                alert("Sales Invoice created successfully!");
                router.push("/daybook");
            } else {
                alert(`Error: ${data.detail || "Failed to create invoice"}`);
            }
        } catch (error) {
            console.error("Failed to create invoice", error);
            alert("Failed to create invoice. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-gray-50 p-8">
            <div className="max-w-5xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Button variant="ghost" size="icon" onClick={() => router.back()}>
                            <ArrowLeft className="h-5 w-5" />
                        </Button>
                        <div>
                            <h1 className="text-3xl font-bold tracking-tight">New Sales Invoice</h1>
                            <p className="text-muted-foreground">Create professional invoices</p>
                        </div>
                    </div>
                    <div className="text-right">
                        <p className="text-sm text-muted-foreground">Grand Total</p>
                        <p className="text-3xl font-bold text-blue-600">₹{grandTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</p>
                    </div>
                </div>

                <form onSubmit={handleSubmit} className="space-y-6">
                    {/* Invoice Details Card */}
                    <Card>
                        <CardHeader>
                            <CardTitle>Invoice Details</CardTitle>
                        </CardHeader>
                        <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            {/* Party Name */}
                            <div className="space-y-2 relative md:col-span-2">
                                <label className="text-sm font-medium">Customer/Party Name *</label>
                                <input
                                    type="text"
                                    placeholder="e.g. ABC Traders"
                                    value={partyName}
                                    onChange={(e) => setPartyName(e.target.value)}
                                    onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
                                    onFocus={() => partySuggestions.length > 0 && setShowSuggestions(true)}
                                    required
                                    className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                />

                                {showSuggestions && partySuggestions.length > 0 && (
                                    <div className="absolute z-10 w-full mt-1 bg-white border rounded-lg shadow-lg max-h-60 overflow-y-auto">
                                        {partySuggestions.map((suggestion, idx) => (
                                            <button
                                                key={idx}
                                                type="button"
                                                onClick={() => {
                                                    setPartyName(suggestion);
                                                    setShowSuggestions(false);
                                                }}
                                                className="w-full px-4 py-2 text-left hover:bg-gray-100 transition-colors"
                                            >
                                                {suggestion}
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>

                            {/* Invoice Number */}
                            <div className="space-y-2">
                                <label className="text-sm font-medium">Invoice Number</label>
                                <input
                                    type="text"
                                    placeholder="Auto-generated"
                                    value={invoiceNumber}
                                    onChange={(e) => setInvoiceNumber(e.target.value)}
                                    className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                />
                            </div>

                            {/* Date */}
                            <div className="space-y-2">
                                <label className="text-sm font-medium">Date *</label>
                                <input
                                    type="date"
                                    value={date}
                                    onChange={(e) => setDate(e.target.value)}
                                    required
                                    className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                />
                            </div>
                        </CardContent>
                    </Card>

                    {/* Line Items Card */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between">
                            <CardTitle>Items</CardTitle>
                            <Button type="button" onClick={addLineItem} size="sm" className="bg-green-600 hover:bg-green-700">
                                <Plus className="h-4 w-4 mr-2" />
                                Add Item
                            </Button>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-4">
                                {/* Header Row */}
                                <div className="grid grid-cols-12 gap-4 font-semibold text-sm text-gray-600 pb-2 border-b">
                                    <div className="col-span-5">Description</div>
                                    <div className="col-span-2">Quantity</div>
                                    <div className="col-span-2">Rate (₹)</div>
                                    <div className="col-span-2">Amount (₹)</div>
                                    <div className="col-span-1"></div>
                                </div>

                                {/* Line Items */}
                                {lineItems.map((item, index) => (
                                    <div key={item.id} className="grid grid-cols-12 gap-4 items-center">
                                        <div className="col-span-5">
                                            <input
                                                type="text"
                                                placeholder="Item description"
                                                value={item.description}
                                                onChange={(e) => updateLineItem(item.id, 'description', e.target.value)}
                                                required
                                                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                            />
                                        </div>
                                        <div className="col-span-2">
                                            <input
                                                type="number"
                                                min="0"
                                                step="0.01"
                                                value={item.quantity}
                                                onChange={(e) => updateLineItem(item.id, 'quantity', parseFloat(e.target.value) || 0)}
                                                required
                                                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                            />
                                        </div>
                                        <div className="col-span-2">
                                            <input
                                                type="number"
                                                min="0"
                                                step="0.01"
                                                value={item.rate}
                                                onChange={(e) => updateLineItem(item.id, 'rate', parseFloat(e.target.value) || 0)}
                                                required
                                                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                            />
                                        </div>
                                        <div className="col-span-2">
                                            <div className="px-3 py-2 bg-gray-50 rounded-lg font-medium">
                                                {item.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                                            </div>
                                        </div>
                                        <div className="col-span-1">
                                            <Button
                                                type="button"
                                                variant="ghost"
                                                size="icon"
                                                onClick={() => removeLineItem(item.id)}
                                                disabled={lineItems.length === 1}
                                                className="text-red-600 hover:text-red-700 hover:bg-red-50"
                                            >
                                                <Trash2 className="h-4 w-4" />
                                            </Button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    </Card>

                    {/* Calculations Card */}
                    <Card>
                        <CardHeader>
                            <CardTitle>Calculation Summary</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-4">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                    {/* Left: Discount & GST */}
                                    <div className="space-y-4">
                                        <div className="space-y-2">
                                            <label className="text-sm font-medium">Discount (%)</label>
                                            <input
                                                type="number"
                                                min="0"
                                                max="100"
                                                step="0.01"
                                                value={discount}
                                                onChange={(e) => setDiscount(parseFloat(e.target.value) || 0)}
                                                className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <label className="text-sm font-medium">GST Rate (%)</label>
                                            <select
                                                value={gstRate}
                                                onChange={(e) => setGstRate(parseFloat(e.target.value))}
                                                className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white"
                                            >
                                                <option value="0">0% (No GST)</option>
                                                <option value="5">5%</option>
                                                <option value="12">12%</option>
                                                <option value="18">18%</option>
                                                <option value="28">28%</option>
                                            </select>
                                        </div>
                                    </div>

                                    {/* Right: Totals */}
                                    <div className="space-y-3 bg-gray-50 p-4 rounded-lg">
                                        <div className="flex justify-between text-sm">
                                            <span className="text-gray-600">Subtotal:</span>
                                            <span className="font-medium">₹{subtotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                                        </div>
                                        {discount > 0 && (
                                            <div className="flex justify-between text-sm">
                                                <span className="text-gray-600">Discount ({discount}%):</span>
                                                <span className="font-medium text-red-600">-₹{discountAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                                            </div>
                                        )}
                                        <div className="flex justify-between text-sm">
                                            <span className="text-gray-600">Taxable Amount:</span>
                                            <span className="font-medium">₹{taxableAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                                        </div>
                                        {gstRate > 0 && (
                                            <div className="flex justify-between text-sm">
                                                <span className="text-gray-600">GST ({gstRate}%):</span>
                                                <span className="font-medium">₹{gstAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                                            </div>
                                        )}
                                        <div className="pt-3 border-t border-gray-300 flex justify-between text-lg">
                                            <span className="font-semibold">Grand Total:</span>
                                            <span className="font-bold text-blue-600">₹{grandTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                                        </div>
                                    </div>
                                </div>

                                {/* Narration */}
                                <div className="space-y-2">
                                    <label className="text-sm font-medium">Narration/Notes</label>
                                    <textarea
                                        placeholder="Additional notes..."
                                        value={narration}
                                        onChange={(e) => setNarration(e.target.value)}
                                        rows={3}
                                        className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                                    />
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Submit Button */}
                    <div className="flex gap-4">
                        <Button
                            type="button"
                            variant="outline"
                            onClick={() => router.back()}
                            className="flex-1"
                        >
                            Cancel
                        </Button>
                        <Button
                            type="submit"
                            disabled={loading}
                            className="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-6 text-lg font-medium"
                        >
                            {loading ? (
                                <>
                                    <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                                    Creating...
                                </>
                            ) : (
                                "Create Invoice & Save to Tally"
                            )}
                        </Button>
                    </div>
                </form>
            </div>
        </div>
    );
}
