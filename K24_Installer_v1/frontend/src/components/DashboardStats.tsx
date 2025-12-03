"use client";

import { useState, useEffect } from "react";

interface KPIStats {
    sales: number;
    sales_change: number;
    receivables: number;
    receivables_change: number;
    payables: number;
    payables_change: number;
    cash: number;
    last_updated: string;
}

function AnimatedNumber({ value, prefix = "" }: { value: number, prefix?: string }) {
    return (
        <span>
            {prefix}{value.toLocaleString('en-IN')}
        </span>
    );
}


export default function DashboardStats() {
    const [stats, setStats] = useState<KPIStats | null>(null);
    // ... (loading logic) ...

    if (!stats) return null;

    const statsData = [
        { label: "Total Sales", value: stats.sales, icon: "💰", prefix: "₹", change: stats.sales_change },
        { label: "Receivables", value: stats.receivables, icon: "📥", prefix: "₹", change: stats.receivables_change },
        { label: "Payables", value: stats.payables, icon: "📤", prefix: "₹", change: stats.payables_change },
        { label: "Cash in Hand", value: stats.cash, icon: "💵", prefix: "₹" }
    ];

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {statsData.map((stat, i) => (
                <div
                    key={i}
                    className="group bg-white rounded-2xl border-2 border-gray-100 p-6 hover:border-purple-200 hover:shadow-xl transition-all duration-300 cursor-pointer transform hover:-translate-y-1"
                >
                    <div className="flex items-start justify-between mb-2">
                        <div className="text-sm font-medium text-gray-600 uppercase tracking-wide">
                            {stat.label}
                        </div>
                        <div className="p-2 bg-gradient-to-br from-purple-50 to-blue-50 rounded-lg group-hover:scale-110 transition-transform">
                            <div className="text-2xl">{stat.icon}</div>
                        </div>
                    </div>
                    <div className="text-4xl font-bold bg-gradient-to-r from-purple-600 to-blue-600 bg-clip-text text-transparent mb-1">
                        <AnimatedNumber value={stat.value} prefix={stat.prefix || ""} />
                    </div>
                    <div className="text-xs text-gray-500 flex items-center gap-1">
                        {stat.change && (
                            <span className={stat.change > 0 ? "text-green-600" : "text-red-600"}>
                                {stat.change > 0 ? "↑" : "↓"} {Math.abs(stat.change)}% from last month
                            </span>
                        )}
                        {!stat.change && <span>Updated just now</span>}
                    </div>
                </div>
            ))}
        </div>
    );
}
