"use client";

import { useEffect, useState, Suspense } from "react";
import MagicInput from "@/components/MagicInput";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";

export default function ChatPage() {
    const [greeting, setGreeting] = useState("Good evening");

    useEffect(() => {
        const updateGreeting = () => {
            const hour = new Date().getHours();
            if (hour >= 5 && hour < 12) {
                setGreeting("Good morning");
            } else if (hour >= 12 && hour < 17) {
                setGreeting("Good afternoon");
            } else {
                setGreeting("Good evening");
            }
        };

        updateGreeting();

        // Focus textarea
        const textarea = document.querySelector('textarea');
        if (textarea) {
            textarea.focus();
        }
    }, []);

    const suggestions = [
        "Show me outstanding receivables",
        "Create a sales invoice for ABC Corp",
        "What's my cash balance today?",
        "Run a compliance audit check"
    ];

    return (
        <div className="min-h-screen bg-[#FAFAF8]">
            {/* Minimal Header */}
            <header className="border-b border-[#E6E3DC]">
                <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
                    <Link
                        href="/"
                        className="flex items-center gap-2 text-[#6B6B6B] hover:text-[#1A1A1A] transition-colors"
                    >
                        <ArrowLeft className="h-4 w-4" />
                        <span className="text-sm">Back</span>
                    </Link>
                    <div className="text-sm text-[#9B9B9B]">KITTU</div>
                </div>
            </header>

            {/* Main Content - Centered, Spacious */}
            <main className="max-w-2xl mx-auto px-6">

                {/* Greeting - Serif, Elegant */}
                <div className="pt-24 pb-12 text-center">
                    <h1 className="text-[32px] font-serif text-[#1A1A1A] mb-3 font-normal tracking-tight">
                        {greeting}, Kiran
                    </h1>
                    <p className="text-[#6B6B6B] text-base">
                        How can I help you with your finances today?
                    </p>
                </div>

                {/* Input - Clean, Centered */}
                <div className="mb-16">
                    <Suspense fallback={<div>Loading...</div>}>
                        <MagicInput
                            isFullPage={true}
                            theme="claude"
                            suggestions={suggestions}
                        />
                    </Suspense>
                </div>

            </main>
        </div>
    );
}
