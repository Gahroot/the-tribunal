"use client";

import { useState } from "react";
import { NeuralNetwork } from "@/components/effects/neural-network";

export default function NeuralDemoPage() {
  const [nodeCount, setNodeCount] = useState(20);
  const [speed, setSpeed] = useState(1);
  const [systemActivity, setSystemActivity] = useState(0.8);

  return (
    <div className="relative w-full h-screen bg-[#0a0a0a]">
      {/* Full screen neural network */}
      <NeuralNetwork
        className="absolute inset-0"
        nodeCount={nodeCount}
        speed={speed}
        systemActivity={systemActivity}
        primaryColor="#7058e3"
        accentColor="#5ee5b3"
        enableGlow={true}
      />

      {/* Overlay controls */}
      <div className="absolute top-4 left-4 bg-black/60 backdrop-blur-md rounded-xl p-5 text-white z-10 border border-white/10">
        <h1 className="text-lg font-semibold mb-4 text-white/90">Neural Network</h1>

        <div className="space-y-4">
          <div>
            <label className="block text-xs text-white/60 mb-1.5">
              Nodes: {nodeCount}
            </label>
            <input
              type="range"
              min={10}
              max={30}
              value={nodeCount}
              onChange={(e) => setNodeCount(Number(e.target.value))}
              className="w-48 accent-[#7058e3]"
            />
          </div>

          <div>
            <label className="block text-xs text-white/60 mb-1.5">
              Speed: {speed.toFixed(1)}x
            </label>
            <input
              type="range"
              min={0.3}
              max={2}
              step={0.1}
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value))}
              className="w-48 accent-[#7058e3]"
            />
          </div>

          <div>
            <label className="block text-xs text-white/60 mb-1.5">
              Activity: {(systemActivity * 100).toFixed(0)}%
            </label>
            <input
              type="range"
              min={0.3}
              max={1}
              step={0.05}
              value={systemActivity}
              onChange={(e) => setSystemActivity(Number(e.target.value))}
              className="w-48 accent-[#7058e3]"
            />
          </div>
        </div>
      </div>

    </div>
  );
}
