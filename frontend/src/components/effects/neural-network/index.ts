/**
 * Neural Network Visualization
 *
 * A 3D particle-based neural network visualization for AI/tech products.
 *
 * Features:
 * - Floating nodes in controlled chaos pattern
 * - Particle streams flowing between nodes
 * - Bloom/glow post-processing effects
 * - Optional data hooks for real metrics integration
 * - Fully customizable colors and behavior
 *
 * Dependencies:
 * - three
 * - @react-three/fiber
 * - @react-three/drei
 * - @react-three/postprocessing
 *
 * Usage:
 * ```tsx
 * import { NeuralNetwork } from '@/components/effects/neural-network';
 *
 * <NeuralNetwork
 *   className="w-full h-screen"
 *   nodeCount={15}
 *   primaryColor="#7058e3"
 *   accentColor="#5ee5b3"
 * />
 * ```
 *
 * With data hooks:
 * ```tsx
 * <NeuralNetwork
 *   nodeCount={agents.length}
 *   nodeStates={agents.map(a => a.isActive ? 'active' : 'idle')}
 *   systemActivity={totalActiveCalls / maxCalls}
 * />
 * ```
 */

export { NeuralNetwork } from './NeuralNetwork';
export type { NeuralNetworkProps, NodeState, Node, Connection, Particle } from './types';
