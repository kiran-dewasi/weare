"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AlertCircle, CheckCircle, AlertTriangle, FileText, Shield, Download } from "lucide-react";

interface AuditIssue {
    severity: string;
    clause: string;
    title: string;
    description: string;
    count: number;
    details: any[];
}

interface AuditReport {
    audit_date: string;
    risk_level: string;
    summary: {
        critical: number;
        warnings: number;
        total_issues: number;
    };
    issues: AuditIssue[];
    recommendations: string[];
}

export default function AuditReport() {
    const [loading, setLoading] = useState(false);
    const [report, setReport] = useState<AuditReport | null>(null);

    const runAudit = async () => {
        setLoading(true);
        try {
            const res = await fetch("http://127.0.0.1:8001/audit/run", {
                headers: {
                    "x-api-key": "k24-secret-key-123"
                }
            });
            const data = await res.json();
            setReport(data);
        } catch (error) {
            console.error("Audit failed:", error);
            alert("Failed to run audit. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    const downloadMarkdown = () => {
        if (!report) return;

        let markdown = `# Pre-Audit Compliance Report\n`;
        markdown += `**Generated:** ${new Date(report.audit_date).toLocaleString()}\n\n`;
        markdown += `**Risk Level:** ${report.risk_level}\n\n`;

        markdown += `## Summary\n\n`;
        markdown += `- Critical Issues: ${report.summary.critical}\n`;
        markdown += `- Warnings: ${report.summary.warnings}\n`;
        markdown += `- Total Issues: ${report.summary.total_issues}\n\n`;

        if (report.issues.length > 0) {
            markdown += `## Issues Found\n\n`;
            report.issues.forEach((issue, idx) => {
                markdown += `### ${idx + 1}. ${issue.title}\n`;
                markdown += `**Severity:** ${issue.severity}\n`;
                markdown += `**Clause:** ${issue.clause}\n`;
                markdown += `**Description:** ${issue.description}\n`;
                if (issue.count > 0) {
                    markdown += `**Occurrences:** ${issue.count}\n`;
                }
                markdown += `\n`;
            });
        }

        if (report.recommendations.length > 0) {
            markdown += `## Recommendations\n\n`;
            report.recommendations.forEach((rec) => {
                markdown += `- ${rec}\n`;
            });
        }

        const blob = new Blob([markdown], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `pre-audit-report-${new Date().toISOString().split('T')[0]}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    const getSeverityColor = (severity: string) => {
        switch (severity) {
            case "CRITICAL": return "bg-red-100 text-red-800 border-red-300";
            case "WARNING": return "bg-yellow-100 text-yellow-800 border-yellow-300";
            default: return "bg-blue-100 text-blue-800 border-blue-300";
        }
    };

    const getRiskBadge = (level: string) => {
        const colors = {
            "HIGH": "bg-red-500",
            "MEDIUM": "bg-yellow-500",
            "LOW": "bg-green-500"
        };
        return <Badge className={`${colors[level as keyof typeof colors] || "bg-gray-500"} text-white`}>{level} RISK</Badge>;
    };

    return (
        <div className="w-full">
            <Card className="border-2 border-[#E6E1D6]">
                <CardHeader className="bg-gradient-to-r from-[#F5F2EB] to-white">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <Shield className="h-6 w-6 text-[#D96C46]" />
                            <div>
                                <CardTitle className="text-2xl font-serif text-[#1A1A1A]">Pre-Audit Agent</CardTitle>
                                <CardDescription className="text-[#686868]">Section 44AB Compliance Check</CardDescription>
                            </div>
                        </div>
                        <div className="flex gap-2">
                            <Button
                                onClick={runAudit}
                                disabled={loading}
                                className="bg-[#D96C46] hover:bg-[#C05A35] text-white transition-all hover:scale-105 active:scale-95"
                            >
                                {loading ? (
                                    <span className="flex items-center gap-2">
                                        <div className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full"></div>
                                        Scanning...
                                    </span>
                                ) : (
                                    <span className="flex items-center gap-2">
                                        <FileText className="h-4 w-4" />
                                        Run Audit Check
                                    </span>
                                )}
                            </Button>
                            {report && (
                                <Button
                                    onClick={downloadMarkdown}
                                    variant="outline"
                                    className="border-[#D96C46] text-[#D96C46] hover:bg-[#D96C46] hover:text-white transition-all hover:scale-105 active:scale-95"
                                >
                                    <Download className="h-4 w-4 mr-2" />
                                    Export Report
                                </Button>
                            )}
                        </div>
                    </div>
                </CardHeader>

                {report && (
                    <CardContent className="pt-6 space-y-6">
                        {/* Summary Card */}
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <Card className="border border-[#E6E1D6]">
                                <CardContent className="pt-4 text-center">
                                    <div className="text-3xl font-bold text-red-600">{report.summary.critical}</div>
                                    <div className="text-sm text-[#686868]">Critical Issues</div>
                                </CardContent>
                            </Card>
                            <Card className="border border-[#E6E1D6]">
                                <CardContent className="pt-4 text-center">
                                    <div className="text-3xl font-bold text-yellow-600">{report.summary.warnings}</div>
                                    <div className="text-sm text-[#686868]">Warnings</div>
                                </CardContent>
                            </Card>
                            <Card className="border border-[#E6E1D6]">
                                <CardContent className="pt-4 text-center">
                                    <div className="text-2xl font-bold mb-2">
                                        {getRiskBadge(report.risk_level)}
                                    </div>
                                    <div className="text-sm text-[#686868]">Overall Risk</div>
                                </CardContent>
                            </Card>
                        </div>

                        {/* Issues List */}
                        {report.issues.length > 0 ? (
                            <div className="space-y-3">
                                <h3 className="font-serif text-lg font-medium text-[#282828]">Issues Found</h3>
                                {report.issues.map((issue, idx) => (
                                    <Card key={idx} className={`border-l-4 ${getSeverityColor(issue.severity)} transition-all hover:shadow-md hover:-translate-y-0.5`}>
                                        <CardContent className="pt-4">
                                            <div className="flex items-start gap-3">
                                                {issue.severity === "CRITICAL" ? (
                                                    <AlertCircle className="h-5 w-5 text-red-600 mt-0.5" />
                                                ) : (
                                                    <AlertTriangle className="h-5 w-5 text-yellow-600 mt-0.5" />
                                                )}
                                                <div className="flex-1">
                                                    <div className="flex items-center justify-between mb-1">
                                                        <h4 className="font-medium text-[#282828]">{issue.title}</h4>
                                                        <Badge variant="outline" className="text-xs">
                                                            {issue.clause}
                                                        </Badge>
                                                    </div>
                                                    <p className="text-sm text-[#686868] mb-2">{issue.description}</p>
                                                    {issue.count > 0 && (
                                                        <p className="text-xs text-[#888888] font-medium">
                                                            {issue.count} occurrence{issue.count > 1 ? "s" : ""} found
                                                        </p>
                                                    )}
                                                </div>
                                            </div>
                                        </CardContent>
                                    </Card>
                                ))}
                            </div>
                        ) : (
                            <Card className="border border-green-200 bg-green-50">
                                <CardContent className="pt-4">
                                    <div className="flex items-center gap-3">
                                        <CheckCircle className="h-6 w-6 text-green-600" />
                                        <div>
                                            <h4 className="font-medium text-green-900">All Clear!</h4>
                                            <p className="text-sm text-green-700">No compliance issues found. Your books look good.</p>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        )}

                        {/* Recommendations */}
                        {report.recommendations.length > 0 && (
                            <div className="space-y-2">
                                <h3 className="font-serif text-lg font-medium text-[#282828]">Recommendations</h3>
                                <Card className="border border-[#E6E1D6] bg-[#F5F2EB]">
                                    <CardContent className="pt-4">
                                        <ul className="space-y-2">
                                            {report.recommendations.map((rec, idx) => (
                                                <li key={idx} className="text-sm text-[#484848] flex items-start gap-2">
                                                    <span className="text-[#D96C46] mt-1">•</span>
                                                    <span>{rec}</span>
                                                </li>
                                            ))}
                                        </ul>
                                    </CardContent>
                                </Card>
                            </div>
                        )}

                        <div className="text-xs text-[#888888] pt-2 border-t">
                            Report generated on {new Date(report.audit_date).toLocaleString()}
                        </div>
                    </CardContent>
                )}
            </Card>
        </div>
    );
}
