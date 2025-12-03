"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
    Building2,
    User,
    Mail,
    Lock,
    ArrowRight,
    ArrowLeft,
    Check,
    Sparkles,
    Shield,
    Zap
} from "lucide-react";
import { useRouter } from "next/navigation";

export default function OnboardingPage() {
    const router = useRouter();
    const [step, setStep] = useState(1);
    const [formData, setFormData] = useState({
        // Step 1: Account
        email: "",
        username: "",
        password: "",
        confirmPassword: "",
        fullName: "",

        // Step 2: Company
        companyName: "",
        gstin: "",
        pan: "",
        address: "",
        city: "",
        state: "",
        pincode: "",
        phone: "",

        // Step 3: Tally
        tallyCompanyName: "",
        tallyUrl: "http://localhost:9000",
        tallyEduMode: false,

        // Step 4: AI
        googleApiKey: ""
    });

    const [errors, setErrors] = useState<Record<string, string>>({});
    const [loading, setLoading] = useState(false);

    const updateField = (field: string, value: any) => {
        setFormData(prev => ({ ...prev, [field]: value }));
        setErrors(prev => ({ ...prev, [field]: "" }));
    };

    const validateStep = (currentStep: number): boolean => {
        const newErrors: Record<string, string> = {};

        if (currentStep === 1) {
            if (!formData.email) newErrors.email = "Email is required";
            if (!formData.username) newErrors.username = "Username is required";
            if (!formData.fullName) newErrors.fullName = "Full name is required";
            if (!formData.password) newErrors.password = "Password is required";
            if (formData.password.length < 8) newErrors.password = "Password must be at least 8 characters";
            if (formData.password !== formData.confirmPassword) newErrors.confirmPassword = "Passwords don't match";
        }

        if (currentStep === 2) {
            if (!formData.companyName) newErrors.companyName = "Company name is required";
            if (!formData.gstin) newErrors.gstin = "GSTIN is required";
        }

        if (currentStep === 3) {
            if (!formData.tallyCompanyName) newErrors.tallyCompanyName = "Tally company name is required";
        }

        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    };

    const handleNext = () => {
        if (validateStep(step)) {
            if (step < 4) setStep(step + 1);
            else handleSubmit();
        }
    };

    const handleSubmit = async () => {
        setLoading(true);
        try {
            // Register user
            const registerRes = await fetch("http://127.0.0.1:8001/auth/register", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    email: formData.email,
                    username: formData.username,
                    password: formData.password,
                    full_name: formData.fullName,
                    company_name: formData.companyName,
                    role: "admin"
                })
            });

            if (!registerRes.ok) {
                const error = await registerRes.json();
                throw new Error(error.detail || "Registration failed");
            }

            const { access_token } = await registerRes.json();
            localStorage.setItem("k24_token", access_token);

            // Setup company
            await fetch("http://127.0.0.1:8001/auth/setup-company", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${access_token}`
                },
                body: JSON.stringify({
                    gstin: formData.gstin,
                    pan: formData.pan,
                    address: formData.address,
                    city: formData.city,
                    state: formData.state,
                    pincode: formData.pincode,
                    phone: formData.phone,
                    tally_company_name: formData.tallyCompanyName,
                    tally_url: formData.tallyUrl,
                    tally_edu_mode: formData.tallyEduMode,
                    google_api_key: formData.googleApiKey
                })
            });

            // Redirect to dashboard
            router.push("/daybook");
        } catch (error: any) {
            alert(error.message);
        } finally {
            setLoading(false);
        }
    };

    const steps = [
        { number: 1, title: "Account", icon: User },
        { number: 2, title: "Company", icon: Building2 },
        { number: 3, title: "Tally Setup", icon: Shield },
        { number: 4, title: "AI Features", icon: Sparkles }
    ];

    return (
        <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50 flex items-center justify-center p-4">
            {/* Background decoration */}
            <div className="absolute inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-0 left-0 w-96 h-96 bg-blue-200 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-blob"></div>
                <div className="absolute top-0 right-0 w-96 h-96 bg-purple-200 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-blob animation-delay-2000"></div>
                <div className="absolute bottom-0 left-1/2 w-96 h-96 bg-pink-200 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-blob animation-delay-4000"></div>
            </div>

            <Card className="w-full max-w-4xl shadow-2xl relative z-10">
                <CardContent className="p-8">
                    {/* Header */}
                    <div className="text-center mb-8">
                        <motion.div
                            initial={{ scale: 0 }}
                            animate={{ scale: 1 }}
                            transition={{ type: "spring", stiffness: 200 }}
                            className="inline-block"
                        >
                            <div className="flex justify-center mb-4">
                                <img
                                    src="/k24-logo.png"
                                    alt="K24 Logo"
                                    className="h-20 w-auto object-contain"
                                />
                            </div>
                        </motion.div>
                        <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
                            Welcome to K24
                        </h1>
                        <p className="text-gray-500 mt-2">Let's set up your intelligent ERP in 4 simple steps</p>
                    </div>

                    {/* Progress Steps */}
                    <div className="flex justify-between mb-12 relative">
                        <div className="absolute top-5 left-0 right-0 h-0.5 bg-gray-200 -z-10"></div>
                        <div
                            className="absolute top-5 left-0 h-0.5 bg-gradient-to-r from-blue-600 to-purple-600 transition-all duration-500 -z-10"
                            style={{ width: `${((step - 1) / 3) * 100}%` }}
                        ></div>

                        {steps.map((s) => {
                            const Icon = s.icon;
                            const isActive = step === s.number;
                            const isComplete = step > s.number;

                            return (
                                <div key={s.number} className="flex flex-col items-center">
                                    <motion.div
                                        className={`w-10 h-10 rounded-full flex items-center justify-center transition-all ${isComplete
                                            ? "bg-gradient-to-br from-blue-600 to-purple-600 text-white"
                                            : isActive
                                                ? "bg-white border-2 border-blue-600 text-blue-600"
                                                : "bg-gray-100 text-gray-400"
                                            }`}
                                        whileHover={{ scale: 1.1 }}
                                    >
                                        {isComplete ? <Check className="w-5 h-5" /> : <Icon className="w-5 h-5" />}
                                    </motion.div>
                                    <span className={`text-xs mt-2 ${isActive ? "text-blue-600 font-semibold" : "text-gray-500"}`}>
                                        {s.title}
                                    </span>
                                </div>
                            );
                        })}
                    </div>

                    {/* Form Content */}
                    <AnimatePresence mode="wait">
                        <motion.div
                            key={step}
                            initial={{ opacity: 0, x: 20 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: -20 }}
                            transition={{ duration: 0.3 }}
                            className="min-h-[400px]"
                        >
                            {step === 1 && <Step1Account formData={formData} updateField={updateField} errors={errors} />}
                            {step === 2 && <Step2Company formData={formData} updateField={updateField} errors={errors} />}
                            {step === 3 && <Step3Tally formData={formData} updateField={updateField} errors={errors} />}
                            {step === 4 && <Step4AI formData={formData} updateField={updateField} errors={errors} />}
                        </motion.div>
                    </AnimatePresence>

                    {/* Navigation */}
                    <div className="flex justify-between mt-8">
                        <Button
                            variant="outline"
                            onClick={() => setStep(step - 1)}
                            disabled={step === 1}
                            className="gap-2"
                        >
                            <ArrowLeft className="w-4 h-4" />
                            Back
                        </Button>

                        <Button
                            onClick={handleNext}
                            disabled={loading}
                            className="bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 gap-2"
                        >
                            {loading ? "Setting up..." : step === 4 ? "Complete Setup" : "Continue"}
                            {!loading && <ArrowRight className="w-4 h-4" />}
                        </Button>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}

// Step Components
function Step1Account({ formData, updateField, errors }: any) {
    return (
        <div className="space-y-4">
            <h2 className="text-2xl font-bold mb-6">Create Your Account</h2>

            <div>
                <label className="block text-sm font-medium mb-2">Full Name</label>
                <div className="relative">
                    <User className="absolute left-3 top-3 w-5 h-5 text-gray-400" />
                    <input
                        type="text"
                        value={formData.fullName}
                        onChange={(e) => updateField("fullName", e.target.value)}
                        className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        placeholder="John Doe"
                    />
                </div>
                {errors.fullName && <p className="text-red-500 text-sm mt-1">{errors.fullName}</p>}
            </div>

            <div>
                <label className="block text-sm font-medium mb-2">Email</label>
                <div className="relative">
                    <Mail className="absolute left-3 top-3 w-5 h-5 text-gray-400" />
                    <input
                        type="email"
                        value={formData.email}
                        onChange={(e) => updateField("email", e.target.value)}
                        className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        placeholder="john@company.com"
                    />
                </div>
                {errors.email && <p className="text-red-500 text-sm mt-1">{errors.email}</p>}
            </div>

            <div>
                <label className="block text-sm font-medium mb-2">Username</label>
                <div className="relative">
                    <User className="absolute left-3 top-3 w-5 h-5 text-gray-400" />
                    <input
                        type="text"
                        value={formData.username}
                        onChange={(e) => updateField("username", e.target.value)}
                        className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        placeholder="johndoe"
                    />
                </div>
                {errors.username && <p className="text-red-500 text-sm mt-1">{errors.username}</p>}
            </div>

            <div className="grid grid-cols-2 gap-4">
                <div>
                    <label className="block text-sm font-medium mb-2">Password</label>
                    <div className="relative">
                        <Lock className="absolute left-3 top-3 w-5 h-5 text-gray-400" />
                        <input
                            type="password"
                            value={formData.password}
                            onChange={(e) => updateField("password", e.target.value)}
                            className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                            placeholder="••••••••"
                        />
                    </div>
                    {errors.password && <p className="text-red-500 text-sm mt-1">{errors.password}</p>}
                </div>

                <div>
                    <label className="block text-sm font-medium mb-2">Confirm Password</label>
                    <div className="relative">
                        <Lock className="absolute left-3 top-3 w-5 h-5 text-gray-400" />
                        <input
                            type="password"
                            value={formData.confirmPassword}
                            onChange={(e) => updateField("confirmPassword", e.target.value)}
                            className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                            placeholder="••••••••"
                        />
                    </div>
                    {errors.confirmPassword && <p className="text-red-500 text-sm mt-1">{errors.confirmPassword}</p>}
                </div>
            </div>
        </div>
    );
}

function Step2Company({ formData, updateField, errors }: any) {
    return (
        <div className="space-y-4">
            <h2 className="text-2xl font-bold mb-6">Company Details</h2>

            <div>
                <label className="block text-sm font-medium mb-2">Company Name *</label>
                <input
                    type="text"
                    value={formData.companyName}
                    onChange={(e) => updateField("companyName", e.target.value)}
                    className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    placeholder="Acme Corporation"
                />
                {errors.companyName && <p className="text-red-500 text-sm mt-1">{errors.companyName}</p>}
            </div>

            <div className="grid grid-cols-2 gap-4">
                <div>
                    <label className="block text-sm font-medium mb-2">GSTIN *</label>
                    <input
                        type="text"
                        value={formData.gstin}
                        onChange={(e) => updateField("gstin", e.target.value)}
                        className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        placeholder="07AABCS1234Q1Z5"
                    />
                    {errors.gstin && <p className="text-red-500 text-sm mt-1">{errors.gstin}</p>}
                </div>

                <div>
                    <label className="block text-sm font-medium mb-2">PAN</label>
                    <input
                        type="text"
                        value={formData.pan}
                        onChange={(e) => updateField("pan", e.target.value)}
                        className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        placeholder="AABCS1234Q"
                    />
                </div>
            </div>

            <div>
                <label className="block text-sm font-medium mb-2">Address</label>
                <input
                    type="text"
                    value={formData.address}
                    onChange={(e) => updateField("address", e.target.value)}
                    className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    placeholder="123, Business Park"
                />
            </div>

            <div className="grid grid-cols-3 gap-4">
                <div>
                    <label className="block text-sm font-medium mb-2">City</label>
                    <input
                        type="text"
                        value={formData.city}
                        onChange={(e) => updateField("city", e.target.value)}
                        className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        placeholder="Delhi"
                    />
                </div>

                <div>
                    <label className="block text-sm font-medium mb-2">State</label>
                    <input
                        type="text"
                        value={formData.state}
                        onChange={(e) => updateField("state", e.target.value)}
                        className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        placeholder="Delhi"
                    />
                </div>

                <div>
                    <label className="block text-sm font-medium mb-2">Pincode</label>
                    <input
                        type="text"
                        value={formData.pincode}
                        onChange={(e) => updateField("pincode", e.target.value)}
                        className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        placeholder="110001"
                    />
                </div>
            </div>

            <div>
                <label className="block text-sm font-medium mb-2">Phone</label>
                <input
                    type="tel"
                    value={formData.phone}
                    onChange={(e) => updateField("phone", e.target.value)}
                    className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    placeholder="+91 98765 43210"
                />
            </div>
        </div>
    );
}

function Step3Tally({ formData, updateField, errors }: any) {
    return (
        <div className="space-y-4">
            <h2 className="text-2xl font-bold mb-6">Connect to Tally</h2>

            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
                <h3 className="font-semibold text-blue-900 mb-2">📌 Before you continue:</h3>
                <ol className="text-sm text-blue-800 space-y-1 list-decimal list-inside">
                    <li>Open Tally on your computer</li>
                    <li>Press F1 → Configuration → Connectivity</li>
                    <li>Enable HTTP Server on Port 9000</li>
                    <li>Load your company</li>
                </ol>
            </div>

            <div>
                <label className="block text-sm font-medium mb-2">Tally Company Name *</label>
                <input
                    type="text"
                    value={formData.tallyCompanyName}
                    onChange={(e) => updateField("tallyCompanyName", e.target.value)}
                    className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    placeholder="Exact name as shown in Tally"
                />
                {errors.tallyCompanyName && <p className="text-red-500 text-sm mt-1">{errors.tallyCompanyName}</p>}
                <p className="text-xs text-gray-500 mt-1">Must match exactly with your Tally company name</p>
            </div>

            <div>
                <label className="block text-sm font-medium mb-2">Tally URL</label>
                <input
                    type="text"
                    value={formData.tallyUrl}
                    onChange={(e) => updateField("tallyUrl", e.target.value)}
                    className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    placeholder="http://localhost:9000"
                />
                <p className="text-xs text-gray-500 mt-1">Default: http://localhost:9000</p>
            </div>

            <div className="flex items-center gap-3 p-4 border rounded-lg">
                <input
                    type="checkbox"
                    id="eduMode"
                    checked={formData.tallyEduMode}
                    onChange={(e) => updateField("tallyEduMode", e.target.checked)}
                    className="w-4 h-4 text-blue-600 rounded focus:ring-2 focus:ring-blue-500"
                />
                <label htmlFor="eduMode" className="text-sm">
                    <span className="font-medium">Tally Educational Mode</span>
                    <p className="text-gray-500 text-xs">Check this if you're using Tally Educational version</p>
                </label>
            </div>
        </div>
    );
}

function Step4AI({ formData, updateField, errors }: any) {
    return (
        <div className="space-y-4">
            <h2 className="text-2xl font-bold mb-6">Enable AI Features</h2>

            <div className="bg-gradient-to-r from-purple-50 to-blue-50 border border-purple-200 rounded-lg p-6 mb-6">
                <div className="flex items-start gap-4">
                    <Sparkles className="w-8 h-8 text-purple-600 flex-shrink-0" />
                    <div>
                        <h3 className="font-semibold text-purple-900 mb-2">Unlock AI-Powered Accounting</h3>
                        <p className="text-sm text-purple-800 mb-3">
                            With Google Gemini AI, you can create vouchers, generate reports, and manage your books using natural language.
                        </p>
                        <ul className="text-sm text-purple-700 space-y-1">
                            <li>✨ "Create receipt from ABC Corp for ₹50,000"</li>
                            <li>✨ "Show me outstanding receivables"</li>
                            <li>✨ "Generate GST report for this month"</li>
                        </ul>
                    </div>
                </div>
            </div>

            <div>
                <label className="block text-sm font-medium mb-2">Google Gemini API Key (Optional)</label>
                <input
                    type="password"
                    value={formData.googleApiKey}
                    onChange={(e) => updateField("googleApiKey", e.target.value)}
                    className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    placeholder="AIza..."
                />
                <p className="text-xs text-gray-500 mt-1">
                    Get your free API key from{" "}
                    <a
                        href="https://makersuite.google.com/app/apikey"
                        target="_blank"
                        className="text-blue-600 hover:underline"
                    >
                        Google AI Studio
                    </a>
                </p>
            </div>

            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                <p className="text-sm text-yellow-800">
                    <strong>Note:</strong> You can skip this step and add your API key later from Settings.
                    K24 will work perfectly fine without AI features.
                </p>
            </div>
        </div>
    );
}
