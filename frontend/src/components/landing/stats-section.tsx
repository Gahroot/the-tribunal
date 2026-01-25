"use client";

import { motion } from "framer-motion";
import { Database, AlertTriangle, TrendingDown } from "lucide-react";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
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

const stats = [
  {
    value: "67%",
    label: "of leads never get a second follow-up",
    icon: AlertTriangle,
  },
  {
    value: "$1.2M",
    label: "average revenue hiding in a 10K contact database",
    icon: Database,
  },
  {
    value: "23x",
    label: "cheaper to reactivate than acquire new",
    icon: TrendingDown,
  },
];

export function StatsSection() {
  return (
    <section className="py-20 px-4 bg-[#f3eff8]" aria-label="Key statistics">
      <motion.div
        className="max-w-6xl mx-auto"
        variants={containerVariants}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true }}
      >
        <motion.div
          className="grid md:grid-cols-3 gap-8"
          variants={containerVariants}
          role="list"
          aria-label="Statistics"
        >
          {stats.map((stat) => (
            <motion.div
              key={stat.value}
              className="text-center p-8 bg-[#f3eff8] rounded-3xl transition-all duration-300 hover:shadow-xl hover:shadow-purple-900/5 hover:-translate-y-1 hover:bg-[#eee9f3]"
              variants={itemVariants}
              role="listitem"
            >
              <stat.icon className="size-7 text-[#8b7fa3] mx-auto mb-5" aria-hidden="true" />
              <div className="text-4xl md:text-5xl font-bold text-[#1a1523] mb-3 font-[family-name:var(--font-serif)]">
                {stat.value}
              </div>
              <p className="text-[#5c566b]">{stat.label}</p>
            </motion.div>
          ))}
        </motion.div>
      </motion.div>
    </section>
  );
}
