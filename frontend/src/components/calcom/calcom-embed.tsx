"use client";

import { useEffect, useCallback, useState } from "react";
import type { Contact } from "@/types";

// Cal.com embed types
declare global {
  interface Window {
    Cal?: CalNamespace;
  }
}

interface CalNamespace {
  (action: string, ...args: unknown[]): void;
  loaded?: boolean;
  ns?: Record<string, CalNamespace>;
  q?: unknown[];
}

interface CalcomEmbedProps {
  calLink: string;
  namespace?: string;
  config?: {
    theme?: "light" | "dark" | "auto";
    hideEventTypeDetails?: boolean;
    layout?: "month_view" | "week_view" | "column_view";
    styles?: {
      branding?: { brandColor?: string };
    };
  };
  contact?: Contact;
  onBookingSuccess?: (data: BookingSuccessData) => void;
  onBookingCancel?: () => void;
  className?: string;
}

interface BookingSuccessData {
  uid: string;
  eventTypeId: number;
  startTime: string;
  endTime: string;
  attendees: Array<{ email: string; name: string }>;
}

// Load Cal.com embed script
function loadCalcomScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.Cal) {
      resolve();
      return;
    }

    const script = document.createElement("script");
    script.src = "https://app.cal.com/embed/embed.js";
    script.async = true;

    script.onload = () => {
      // Wait for Cal to be available
      const checkCal = () => {
        if (window.Cal) {
          resolve();
        } else {
          setTimeout(checkCal, 50);
        }
      };
      checkCal();
    };

    script.onerror = () => reject(new Error("Failed to load Cal.com embed script"));

    document.head.appendChild(script);
  });
}

// Inline Embed Component
export function CalcomInlineEmbed({
  calLink,
  namespace = "default",
  config,
  contact,
  onBookingSuccess,
  onBookingCancel,
  className,
}: CalcomEmbedProps) {
  const [isLoaded, setIsLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadCalcomScript()
      .then(() => {
        setIsLoaded(true);
      })
      .catch((err) => {
        setError(err.message);
      });
  }, []);

  useEffect(() => {
    if (!isLoaded || !window.Cal) return;

    const Cal = window.Cal;

    // Initialize namespace
    Cal("init", namespace, { origin: "https://app.cal.com" });

    // Configure the embed
    const embedConfig = {
      ...config,
      ...(contact && {
        name: `${contact.first_name} ${contact.last_name || ""}`.trim(),
        email: contact.email,
        ...(contact.phone_number && { phone: contact.phone_number }),
        metadata: {
          contact_id: contact.id,
          source: "crm",
        },
      }),
    };

    Cal(namespace, "inline", {
      elementOrSelector: `#cal-inline-${namespace}`,
      calLink,
      config: embedConfig,
    });

    // Set up event listeners
    Cal(namespace, "on", {
      action: "bookingSuccessful",
      callback: (e: { detail: { data: BookingSuccessData } }) => {
        onBookingSuccess?.(e.detail.data);
      },
    });

    Cal(namespace, "on", {
      action: "bookingCancelled",
      callback: () => {
        onBookingCancel?.();
      },
    });

    // Apply UI config
    Cal(namespace, "ui", {
      theme: config?.theme || "auto",
      hideEventTypeDetails: config?.hideEventTypeDetails || false,
      layout: config?.layout || "month_view",
      styles: config?.styles,
    });
  }, [isLoaded, calLink, namespace, config, contact, onBookingSuccess, onBookingCancel]);

  if (error) {
    return (
      <div className="flex items-center justify-center p-8 text-red-500">
        Failed to load booking calendar: {error}
      </div>
    );
  }

  if (!isLoaded) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  return (
    <div
      id={`cal-inline-${namespace}`}
      className={className}
      style={{ width: "100%", height: "100%", minHeight: "500px" }}
    />
  );
}

// Popup Embed Component
interface CalcomPopupEmbedProps extends CalcomEmbedProps {
  trigger: React.ReactNode;
}

export function CalcomPopupEmbed({
  calLink,
  namespace = "popup",
  config,
  contact,
  onBookingSuccess,
  onBookingCancel,
  trigger,
}: CalcomPopupEmbedProps) {
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    loadCalcomScript()
      .then(() => {
        setIsLoaded(true);
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!isLoaded || !window.Cal) return;

    const Cal = window.Cal;

    Cal("init", namespace, { origin: "https://app.cal.com" });

    // Set up event listeners
    Cal(namespace, "on", {
      action: "bookingSuccessful",
      callback: (e: { detail: { data: BookingSuccessData } }) => {
        onBookingSuccess?.(e.detail.data);
      },
    });

    Cal(namespace, "on", {
      action: "bookingCancelled",
      callback: () => {
        onBookingCancel?.();
      },
    });

    Cal(namespace, "ui", {
      theme: config?.theme || "auto",
      hideEventTypeDetails: config?.hideEventTypeDetails || false,
      styles: config?.styles,
    });
  }, [isLoaded, namespace, config, onBookingSuccess, onBookingCancel]);

  const openPopup = useCallback(() => {
    if (!window.Cal) return;

    const Cal = window.Cal;
    const embedConfig = {
      ...config,
      ...(contact && {
        name: `${contact.first_name} ${contact.last_name || ""}`.trim(),
        email: contact.email,
        ...(contact.phone_number && { phone: contact.phone_number }),
        metadata: {
          contact_id: contact.id,
          source: "crm",
        },
      }),
    };

    Cal(namespace, "modal", {
      calLink,
      config: embedConfig,
    });
  }, [calLink, namespace, config, contact]);

  if (!isLoaded) {
    return (
      <div className="opacity-50 cursor-not-allowed">
        {trigger}
      </div>
    );
  }

  return (
    <div onClick={openPopup} className="cursor-pointer">
      {trigger}
    </div>
  );
}

// Floating Button Component
interface CalcomFloatingButtonProps extends CalcomEmbedProps {
  buttonText?: string;
  buttonColor?: string;
  position?: "bottom-right" | "bottom-left";
}

export function CalcomFloatingButton({
  calLink,
  namespace = "floating",
  config,
  contact,
  onBookingSuccess,
  onBookingCancel,
  buttonText = "Book a call",
  buttonColor = "#0066ff",
  position = "bottom-right",
}: CalcomFloatingButtonProps) {
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    loadCalcomScript()
      .then(() => {
        setIsLoaded(true);
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!isLoaded || !window.Cal) return;

    const Cal = window.Cal;

    Cal("init", namespace, { origin: "https://app.cal.com" });

    // Set up event listeners
    Cal(namespace, "on", {
      action: "bookingSuccessful",
      callback: (e: { detail: { data: BookingSuccessData } }) => {
        onBookingSuccess?.(e.detail.data);
      },
    });

    Cal(namespace, "on", {
      action: "bookingCancelled",
      callback: () => {
        onBookingCancel?.();
      },
    });

    Cal(namespace, "ui", {
      theme: config?.theme || "auto",
      hideEventTypeDetails: config?.hideEventTypeDetails || false,
      styles: config?.styles,
    });

    // Create floating button
    const embedConfig = {
      ...config,
      ...(contact && {
        name: `${contact.first_name} ${contact.last_name || ""}`.trim(),
        email: contact.email,
        ...(contact.phone_number && { phone: contact.phone_number }),
        metadata: {
          contact_id: contact.id,
          source: "crm",
        },
      }),
    };

    Cal(namespace, "floatingButton", {
      calLink,
      config: embedConfig,
      buttonText,
      buttonColor,
      buttonPosition: position,
    });
  }, [isLoaded, calLink, namespace, config, contact, buttonText, buttonColor, position, onBookingSuccess, onBookingCancel]);

  return null; // Floating button is injected by Cal.com
}

// Hook for programmatic Cal.com control
export function useCalcom(namespace: string = "default") {
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    loadCalcomScript()
      .then(() => {
        setIsLoaded(true);
      })
      .catch(console.error);
  }, []);

  const openModal = useCallback(
    (calLink: string, config?: Record<string, unknown>) => {
      if (!window.Cal) return;
      window.Cal(namespace, "modal", { calLink, config });
    },
    [namespace]
  );

  const preload = useCallback(
    (calLink: string) => {
      if (!window.Cal) return;
      window.Cal(namespace, "preload", { calLink });
    },
    [namespace]
  );

  return {
    isLoaded,
    openModal,
    preload,
    Cal: window.Cal,
  };
}
