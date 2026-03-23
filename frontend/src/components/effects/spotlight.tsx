import { cn } from "@/lib/utils";

interface SpotlightProps {
  className?: string;
}

export function Spotlight({ className }: SpotlightProps) {
  return (
    <div
      className={cn(
        "absolute inset-0 overflow-hidden pointer-events-none",
        className
      )}
    >
      {/* Top-left purple bloom */}
      <div
        className="absolute -top-40 -left-40 w-[800px] h-[800px] bg-primary/40 rounded-full blur-[100px]"
        style={{
          animation: "spotlight-in 1s ease-out forwards, drift 20s ease-in-out infinite alternate",
        }}
      />
      {/* Top-right mint bloom */}
      <div
        className="absolute -top-20 right-0 w-[600px] h-[600px] bg-success/20 rounded-full blur-[100px]"
        style={{
          animation: "spotlight-in 1s ease-out 0.2s forwards, drift 25s ease-in-out infinite alternate-reverse",
          opacity: 0,
        }}
      />
      {/* Center ambient glow */}
      <div
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[1000px] h-[1000px] bg-primary/15 rounded-full blur-[150px]"
        style={{
          animation: "spotlight-in 1s ease-out 0.4s forwards, drift 30s ease-in-out infinite alternate",
          opacity: 0,
        }}
      />
    </div>
  );
}
