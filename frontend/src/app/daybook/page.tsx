"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

interface Voucher {
    id: number;
    voucher_number: string;
    date: string;
    voucher_type: string;
    party_name: string;
    amount: number;
    narration: string | null;
}

export default function DaybookDashboard() {
    const [vouchers, setVouchers] = useState<Voucher[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch("http://127.0.0.1:8001/reports/daybook", {
            headers: {
                "x-api-key": "k24-secret-key-123"
            }
        })
            .then(res => res.json())
            .then(data => {
                // Handle both array and object responses
                const voucherData = Array.isArray(data) ? data : (data.vouchers || []);
                setVouchers(voucherData);
                setLoading(false);
            })
            .catch(err => {
                console.error("Failed to load daybook:", err);
                setVouchers([]); // Set empty array on error
                setLoading(false);
            });
    }, []);

    if (loading) {
        return <div className="p-8">Loading Daybook...</div>;
    }

    return (
        <div className="p-8 space-y-6">
            <div>
                <h1 className="text-3xl font-bold">Daybook</h1>
                <p className="text-muted-foreground">Today's Activity</p>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle>Transactions</CardTitle>
                </CardHeader>
                <CardContent>
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Date</TableHead>
                                <TableHead>Type</TableHead>
                                <TableHead>Party</TableHead>
                                <TableHead>Vch No</TableHead>
                                <TableHead className="text-right">Amount</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {vouchers.map((voucher) => (
                                <TableRow key={voucher.id}>
                                    <TableCell>{new Date(voucher.date).toLocaleDateString()}</TableCell>
                                    <TableCell>
                                        <Badge variant={voucher.voucher_type === 'Sales' ? 'default' : 'secondary'}>
                                            {voucher.voucher_type}
                                        </Badge>
                                    </TableCell>
                                    <TableCell className="font-medium">{voucher.party_name}</TableCell>
                                    <TableCell>{voucher.voucher_number}</TableCell>
                                    <TableCell className="text-right font-bold">
                                        ₹{voucher.amount.toLocaleString('en-IN')}
                                    </TableCell>
                                </TableRow>
                            ))}
                            {vouchers.length === 0 && (
                                <TableRow>
                                    <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                                        No transactions today.
                                    </TableCell>
                                </TableRow>
                            )}
                        </TableBody>
                    </Table>
                </CardContent>
            </Card>
        </div>
    );
}
