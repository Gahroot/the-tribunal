/**
 * Neural Network Visualization Types
 * Standalone component - can be extracted to separate package
 */

export interface NeuralNetworkProps {
  /** Number of nodes to display (default: 12) */
  nodeCount?: number;
  /** Number of particle streams between nodes (default: 8) */
  connectionCount?: number;
  /** Primary color for nodes and particles (default: #7058e3) */
  primaryColor?: string;
  /** Secondary/accent color for particles (default: #5ee5b3) */
  accentColor?: string;
  /** Background color (default: transparent) */
  backgroundColor?: string;
  /** Animation speed multiplier (default: 1) */
  speed?: number;
  /** Enable/disable glow effects (default: true) */
  enableGlow?: boolean;
  /** Enable/disable particle trails (default: true) */
  enableTrails?: boolean;
  /** CSS class for container */
  className?: string;
  /** Optional callback when a node is clicked */
  onNodeClick?: (nodeId: number) => void;

  // Data hooks for optional real metrics integration
  /** Optional: Array of node states (idle, active, processing) */
  nodeStates?: NodeState[];
  /** Optional: Array of connection activity levels (0-1) */
  connectionActivity?: number[];
  /** Optional: Overall system activity level (0-1) */
  systemActivity?: number;
}

export type NodeState = "idle" | "active" | "processing" | "error";

export interface Node {
  id: number;
  position: [number, number, number];
  velocity: [number, number, number];
  state: NodeState;
  size: number;
  pulsePhase: number;
}

export interface Connection {
  id: number;
  from: number;
  to: number;
  particles: Particle[];
  activity: number;
}

export interface Particle {
  progress: number;
  speed: number;
  offset: [number, number];
  color: "primary" | "accent";
}
