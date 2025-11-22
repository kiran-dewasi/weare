"use client";

import { useEffect } from "react";
import MagicInput from "@/components/MagicInput";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";

export default function ChatPage() {
    useEffect(() => {
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
                        Good evening, Kiran
                    </h1>
                    <p className="text-[#6B6B6B] text-base">
                        How can I help you with your finances today?
                    </p>
                </div>

                {/* Input - Clean, Centered */}
                <div className="mb-16">
                    <MagicInput isFullPage={true} theme="claude" />
                </div>

                {/* Suggestions - Minimal */}
                <div className="pb-24">
                    <div className="text-xs text-[#9B9B9B] mb-4 uppercase tracking-wider">
                        Suggestions
                    </div>
                    <div className="space-y-2">
                        {suggestions.map((suggestion, idx) => (
                            <button
                                key={idx}
                                onClick={() => {
                                    const textarea = document.querySelector('textarea');
                                    if (textarea) {
                                        textarea.value = suggestion;
                                        textarea.focus();
                                    }
                                }}
                                className="w-full text-left px-4 py-3 text-[14px] text-[#1A1A1A] bg-white hover:bg-[#F5F2EB] border border-[#E6E3DC] rounded-lg transition-colors"
                            >
                                {suggestion}
                            </button>
                        ))}
                    </div>
                </div>

            </main>
        </div>
    );
}
