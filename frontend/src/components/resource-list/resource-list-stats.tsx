"use client";

import { useState, useEffect } from "react";
import { motion } from "motion/react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";

function AnimatedNumber({ value }: { value: number }) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    const end = value;
    if (end === 0) return;
    const duration = 1000;
    const startTime = performance.now();

    const step = (currentTime: number) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.floor(eased * end));
      if (progress < 1) requestAnimationFrame(step);
    };

    requestAnimationFrame(step);
  }, [value]);

  return <span>{display.toLocaleString()}</span>;
}

interface StatItem {
  label: string;
  value: string | number;
}

interface ResourceListStatsProps {
  stats: StatItem[];
  columns?: 3 | 4;
  animated?: boolean;
}

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.05 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 },
};

export function ResourceListStats({ stats, columns = 4, animated = true }: ResourceListStatsProps) {
  const gridClass = columns === 3 ? "grid gap-4 md:grid-cols-3" : "grid gap-4 md:grid-cols-4";

  if (animated) {
    return (
      <motion.div
        className={gridClass}
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {stats.map((stat) => (
          <motion.div key={stat.label} variants={itemVariants}>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>{stat.label}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold tabular-nums">
                  {typeof stat.value === "number" ? <AnimatedNumber value={stat.value} /> : stat.value}
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </motion.div>
    );
  }

  return (
    <div className={gridClass}>
      {stats.map((stat) => (
        <Card key={stat.label}>
          <CardHeader className="pb-2">
            <CardDescription>{stat.label}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold tabular-nums">
              {typeof stat.value === "number" ? <AnimatedNumber value={stat.value} /> : stat.value}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
