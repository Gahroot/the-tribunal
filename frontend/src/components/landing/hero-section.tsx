"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Phone,
  MessageSquare,
  Loader2,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent } from "@/components/ui/card";
import { PhoneInput, normalizeToE164 } from "./phone-input";
import { publicDemoApi } from "@/lib/api/public-demo";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.15,
    },
  },
} as const;

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.5,
      ease: "easeOut" as const,
    },
  },
} as const;

export function HeroSection() {
  const [phone, setPhone] = useState("");

  const callMutation = useMutation({
    mutationFn: (phoneNumber: string) => publicDemoApi.triggerCall(phoneNumber),
  });

  const textMutation = useMutation({
    mutationFn: (phoneNumber: string) => publicDemoApi.triggerText(phoneNumber),
  });

  const handleCall = () => {
    const normalized = normalizeToE164(phone);
    if (normalized.length >= 12) {
      callMutation.mutate(normalized);
    }
  };

  const handleText = () => {
    const normalized = normalizeToE164(phone);
    if (normalized.length >= 12) {
      textMutation.mutate(normalized);
    }
  };

  const isPhoneValid = normalizeToE164(phone).length >= 12;
  const isPending = callMutation.isPending || textMutation.isPending;
  const isSuccess = callMutation.isSuccess || textMutation.isSuccess;
  const successMessage = callMutation.data?.message || textMutation.data?.message;
  const error = callMutation.error || textMutation.error;
  const isError = callMutation.isError || textMutation.isError;

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-16 bg-white">
      <motion.div
        className="max-w-6xl w-full grid lg:grid-cols-2 gap-12 lg:gap-20 items-center"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* Left side - Headline */}
        <motion.div className="space-y-6" variants={itemVariants}>
          <p className="text-sm font-medium text-violet-600 tracking-wide uppercase">
            AI Voice Agent
          </p>
          <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold tracking-tight text-gray-900 leading-[1.1]">
            Voice AI built for every customer conversation
          </h1>
          <p className="text-lg text-gray-600 max-w-md">
            Let our AI handle calls and texts so you can focus on closing deals.
          </p>
        </motion.div>

        {/* Right side - Form */}
        <motion.div variants={itemVariants}>
          <Card className="border border-gray-200 shadow-sm">
            <CardContent className="pt-6">
              <div className="space-y-2 mb-6">
                <h2 className="text-xl md:text-2xl font-semibold text-card-foreground">
                  Don&apos;t believe us?
                </h2>
                <p className="text-lg text-muted-foreground">
                  Have our AI give you a call.
                </p>
              </div>

              <div aria-live="polite" role="status">
                {isSuccess && (
                  <div className="py-6 space-y-3">
                    <CheckCircle2 className="size-12 text-green-500" aria-hidden="true" />
                    <p className="text-green-400 font-medium text-lg">
                      {successMessage}
                    </p>
                  </div>
                )}
              </div>

              {!isSuccess && (
                <div className="space-y-4">
                  <div>
                    <label htmlFor="phone-input" className="block text-sm font-medium text-muted-foreground mb-1">
                      Phone Number
                    </label>
                    <PhoneInput
                      id="phone-input"
                      value={phone}
                      onChange={setPhone}
                      disabled={isPending}
                      aria-describedby={isError ? "phone-error" : undefined}
                      aria-invalid={isError}
                      className="h-12"
                    />
                  </div>

                  {isError && (
                    <Alert id="phone-error" variant="destructive" role="alert">
                      <AlertCircle className="size-4" aria-hidden="true" />
                      <AlertDescription>
                        {(error as Error)?.message ||
                          "Something went wrong. Please try again."}
                      </AlertDescription>
                    </Alert>
                  )}

                  <Button
                    type="button"
                    size="lg"
                    className="w-full h-12 bg-violet-600 hover:bg-violet-700 text-white font-semibold"
                    disabled={!isPhoneValid || isPending}
                    onClick={handleCall}
                  >
                    {callMutation.isPending ? (
                      <>
                        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                        <span>Calling...</span>
                      </>
                    ) : (
                      <>
                        <Phone className="size-4" aria-hidden="true" />
                        Let&apos;s Talk
                      </>
                    )}
                  </Button>

                  <Button
                    type="button"
                    size="lg"
                    variant="outline"
                    className="w-full h-12 font-semibold"
                    disabled={!isPhoneValid || isPending}
                    onClick={handleText}
                  >
                    {textMutation.isPending ? (
                      <>
                        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                        <span>Sending...</span>
                      </>
                    ) : (
                      <>
                        <MessageSquare className="size-4" aria-hidden="true" />
                        I&apos;d rather text
                      </>
                    )}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>
      </motion.div>
    </div>
  );
}
