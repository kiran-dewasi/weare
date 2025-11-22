"use client";

import { useState, useEffect } from "react";

interface KPIStats {
    sales: number;
    receivables: number;
    payables: number;
    cash: number;
    last_updated: string;
}

function AnimatedNumber({ value, prefix = "" }: { value: number; prefix?: string }) {
    const [displayValue, setDisplayValue] = useState(0);

    useEffect(() => {
        const startTime = performance.now();
        const duration = 1500;

        const animate = (currentTime: number) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);

            // Easing function (easeOutQuart for satisfying deceleration)
            const easeOutQuart = 1 - Math.pow(1 - progress, 4);
            const current = Math.floor(value * easeOutQuart);

            setDisplayValue(current);

            if (progress < 1) {
                requestAnimationFrame(animate);
            } else {
                setDisplayValue(value);
            }
        };

        requestAnimationFrame(animate);
    }, [value]);

    return (
        <span>
            {prefix}{displayValue.toLocaleString('en-IN')}
        </span>
    );
}

export default function DashboardStats() {
    const [stats, setStats] = useState<KPIStats | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch("http://127.0.0.1:8001/dashboard/kpi", {
            headers: {
                "x-api-key": "k24-secret-key-123"
            }
        })
            .then((res) => res.json())
            .then((data) => {
                setStats(data);
                setLoading(false);
            })
            .catch((err) => {
                console.error("Failed to fetch KPIs:", err);
                setLoading(false);
            });
    }, []);

    if (loading) {
        return (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="bg-white rounded-2xl border-2 border-gray-100 p-6 animate-pulse">
                        <div className="h-4 bg-gray-200 rounded w-1/2 mb-3"></div>
                        <div className="h-8 bg-gray-200 rounded w-3/4 mb-2"></div>
                        <div className="h-3 bg-gray-200 rounded w-1/3"></div>
                    </div>
                ))}
            </div>
        );
    }

    if (!stats) return null;

    const statsData = [
        { label: "Total Sales", value: stats.sales, icon: "💰", prefix: "₹", change: 12 },
        { label: "Receivables", value: stats.receivables, icon: "📥", prefix: "₹", change: -5 },
        { label: "Payables", value: stats.payables, icon: "📤", prefix: "₹", change: 3 },
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
