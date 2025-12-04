"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Search, CheckCircle2 } from "lucide-react";
import { useState, useEffect } from "react";

export default function Navbar() {
    const pathname = usePathname();
    const router = useRouter();
    const [searchQuery, setSearchQuery] = useState("");
    const [isSyncing, setIsSyncing] = useState(false);
    const [showSuccess, setShowSuccess] = useState(false);
    const [syncHealth, setSyncHealth] = useState<{ connected: boolean; lastSync: string | null }>({ connected: false, lastSync: null });

    // Poll sync status
    useEffect(() => {
        const checkHealth = async () => {
            try {
                const res = await fetch("http://127.0.0.1:8001/sync/status", {
                    headers: { "x-api-key": "k24-secret-key-123" }
                });
                const data = await res.json();
                const newStatus = {
                    connected: data.tally_connected,
                    lastSync: data.last_sync_time
                };
                setSyncHealth(newStatus);

                // Persist to localStorage for next page load
                localStorage.setItem('k24_sync_status', JSON.stringify(newStatus));
            } catch (e) {
                setSyncHealth({ connected: false, lastSync: null });
                localStorage.setItem('k24_sync_status', JSON.stringify({ connected: false, lastSync: null }));
            }
        };

        // Load cached status first (optimistic UI)
        const cached = localStorage.getItem('k24_sync_status');
        if (cached) {
            try {
                setSyncHealth(JSON.parse(cached));
            } catch (e) {
                console.error('Failed to parse cached sync status');
            }
        }

        // Then check actual status
        checkHealth();
        const interval = setInterval(checkHealth, 30000); // Check every 30s
        return () => clearInterval(interval);
    }, []);

    const handleSync = async () => {
        setIsSyncing(true);
        try {
            const res = await fetch("http://127.0.0.1:8001/sync", {
                method: "POST",
                headers: {
                    "x-api-key": "k24-secret-key-123"
                }
            });
            if (res.ok) {
                // Show green success notification
                setShowSuccess(true);
                setTimeout(() => {
                    setShowSuccess(false);
                    window.location.reload(); // Refresh to show new data
                }, 2000);
            } else {
                const error = await res.json();
                alert(`Sync Failed: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error("Sync error:", error);
            alert("Sync Error: Is backend running?");
        } finally {
            setIsSyncing(false);
        }
    };

    const handleSearch = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && searchQuery.trim()) {
            router.push(`/search?q=${encodeURIComponent(searchQuery)}`);
        }
    };

    const routes = [
        {
            href: "/",
            label: "Receivables",
            active: pathname === "/",
        },
        {
            href: "/daybook",
            label: "Daybook",
            active: pathname === "/daybook",
        },
    ];

    return (
        <>
            {/* Success Notification */}
            {showSuccess && (
                <div className="fixed top-4 right-4 z-50 bg-green-500 text-white px-6 py-3 rounded-lg shadow-lg flex items-center gap-2 animate-in slide-in-from-top">
                    <CheckCircle2 className="h-5 w-5" />
                    <span className="font-medium">Sync Completed Successfully!</span>
                </div>
            )}

            <nav className="border-b bg-white px-8 py-4 flex items-center justify-between sticky top-0 z-50">
                <div className="flex items-center gap-8">
                    <Link href="/" className="text-2xl font-bold text-primary tracking-tight">
                        K24
                    </Link>
                    <div className="flex items-center gap-4">
                        {routes.map((route) => (
                            <Link
                                key={route.href}
                                href={route.href}
                                className={cn(
                                    "text-sm font-medium transition-colors hover:text-primary",
                                    route.active ? "text-black" : "text-muted-foreground"
                                )}
                            >
                                {route.label}
                            </Link>
                        ))}
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    <div className="relative w-64">
                        <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                        <Input
                            placeholder="Search anything..."
                            className="pl-8"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            onKeyDown={handleSearch}
                            suppressHydrationWarning
                        />
                    </div>
                    <div className="flex items-center gap-2 mr-2">
                        <div
                            className={cn("h-2.5 w-2.5 rounded-full transition-colors", syncHealth.connected ? "bg-green-500" : "bg-red-500")}
                            title={syncHealth.connected ? `Tally Connected (Last Sync: ${syncHealth.lastSync ? new Date(syncHealth.lastSync).toLocaleTimeString() : 'Never'})` : "Tally Disconnected"}
                        />
                        <span className="text-xs text-muted-foreground hidden sm:inline">
                            {syncHealth.connected ? "Online" : "Offline"}
                        </span>
                    </div>
                    <Button size="sm" variant="outline" onClick={handleSync} disabled={isSyncing}>
                        {isSyncing ? "Syncing..." : "Sync Now"}
                    </Button>
                </div>
            </nav>
        </>
    );
}
