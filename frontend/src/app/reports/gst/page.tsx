"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowLeft, FileText, Scale } from "lucide-react";
import Link from "next/link";

interface GSTData {
    period: string;
    gstr1: {
        label: string;
        taxable_value: number;
        tax_amount: number;
    };
    gstr3b: {
        label: string;
        taxable_value: number;
        tax_amount: number;
    };
    net_payable: number;
}

export default function GSTPage() {
    const [data, setData] = useState<GSTData | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch("http://127.0.0.1:8001/reports/gst-summary", {
            headers: { "x-api-key": "k24-secret-key-123" }
        })
            .then(res => res.json())
            .then(setData)
            .catch(console.error)
            .finally(() => setLoading(false));
    }, []);

    if (loading) {
        return (
            <div className="min-h-screen bg-gray-50 p-8 flex items-center justify-center">
                <div className="animate-pulse flex flex-col items-center gap-4">
                    <div className="h-12 w-12 bg-gray-200 rounded-full"></div>
                    <div className="h-4 w-32 bg-gray-200 rounded"></div>
                </div>
            </div>
        );
    }

    if (!data) return <div>Error loading report</div>;

    return (
        <div className="min-h-screen bg-[#FAFAF8] text-[#1A1A1A] font-sans">
            {/* Header */}
            <header className="sticky top-0 z-10 bg-white/80 backdrop-blur-md border-b border-gray-200 px-6 py-4">
                <div className="max-w-6xl mx-auto flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Link href="/" className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
                            <ArrowLeft className="h-5 w-5 text-gray-500" />
                        </Link>
                        <div>
                            <h1 className="text-xl font-semibold tracking-tight">GST Summary</h1>
                            <p className="text-xs text-gray-500">{data.period}</p>
                        </div>
                    </div>
                    <div className="flex gap-2">
                        <button className="px-3 py-1.5 text-sm font-medium bg-black text-white rounded-md hover:bg-gray-800 transition-colors">
                            Export PDF
                        </button>
                    </div>
                </div>
            </header>

            <main className="max-w-6xl mx-auto px-6 py-8 space-y-8">
                {/* Net Payable Card */}
                <Card className="border-none shadow-sm bg-blue-50">
                    <CardContent className="p-8 flex flex-col items-center justify-center text-center">
                        <div className="p-3 bg-blue-100 rounded-full mb-4">
                            <Scale className="h-8 w-8 text-blue-600" />
                        </div>
                        <p className="text-sm font-medium text-blue-600 mb-1">Estimated Net Payable</p>
                        <div className="text-5xl font-bold tracking-tight text-blue-800">
                            ₹{data.net_payable.toLocaleString('en-IN')}
                        </div>
                        <p className="text-xs text-blue-500 mt-2">Output Tax - Input Tax Credit</p>
                    </CardContent>
                </Card>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                    {/* GSTR-1 (Output) */}
                    <Card className="border-none shadow-sm bg-white">
                        <CardHeader className="border-b border-gray-100 pb-4">
                            <CardTitle className="text-lg font-medium flex items-center gap-2">
                                <FileText className="h-5 w-5 text-gray-500" />
                                {data.gstr1.label}
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="p-6 space-y-4">
                            <div className="flex justify-between items-center">
                                <span className="text-sm text-gray-500">Taxable Value</span>
                                <span className="font-medium">₹{data.gstr1.taxable_value.toLocaleString('en-IN')}</span>
                            </div>
                            <div className="flex justify-between items-center pt-4 border-t border-gray-50">
                                <span className="text-sm font-semibold text-gray-900">Output Tax Liability</span>
                                <span className="font-bold text-lg text-red-600">₹{data.gstr1.tax_amount.toLocaleString('en-IN')}</span>
                            </div>
                        </CardContent>
                    </Card>

                    {/* GSTR-3B (Input) */}
                    <Card className="border-none shadow-sm bg-white">
                        <CardHeader className="border-b border-gray-100 pb-4">
                            <CardTitle className="text-lg font-medium flex items-center gap-2">
                                <FileText className="h-5 w-5 text-gray-500" />
                                {data.gstr3b.label}
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="p-6 space-y-4">
                            <div className="flex justify-between items-center">
                                <span className="text-sm text-gray-500">Taxable Purchases</span>
                                <span className="font-medium">₹{data.gstr3b.taxable_value.toLocaleString('en-IN')}</span>
                            </div>
                            <div className="flex justify-between items-center pt-4 border-t border-gray-50">
                                <span className="text-sm font-semibold text-gray-900">Eligible ITC</span>
                                <span className="font-bold text-lg text-green-600">₹{data.gstr3b.tax_amount.toLocaleString('en-IN')}</span>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </main>
        </div>
    );
}
