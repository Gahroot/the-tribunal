"use client";

import { useRef, useMemo, useEffect } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import * as THREE from "three";
import type { NeuralNetworkProps } from "./types";

// Default colors matching Prestyj/AICRM theme
const DEFAULT_PRIMARY = "#7058e3";
const DEFAULT_ACCENT = "#5ee5b3";

// Seeded random for deterministic results
function seededRandom(seed: number): () => number {
  return () => {
    seed = (seed * 9301 + 49297) % 233280;
    return seed / 233280;
  };
}

interface NetworkNode {
  id: number;
  position: THREE.Vector3;
  layer: number;
  connections: number[];
  pulsePhase: number;
  isCore: boolean;
}

interface Pulse {
  connectionIndex: number;
  progress: number;
  speed: number;
  direction: 1 | -1;
}

// Central glowing core
function CoreNode({ color }: { color: THREE.Color }) {
  const groupRef = useRef<THREE.Group>(null);
  const innerRef = useRef<THREE.Mesh>(null);
  const ringsRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (!groupRef.current || !innerRef.current || !ringsRef.current) return;
    const time = state.clock.elapsedTime;

    // Pulsing core
    const pulse = 1 + Math.sin(time * 2) * 0.1;
    innerRef.current.scale.setScalar(pulse);

    // Rotating rings
    ringsRef.current.rotation.x = time * 0.5;
    ringsRef.current.rotation.y = time * 0.3;
    ringsRef.current.rotation.z = time * 0.2;
  });

  return (
    <group ref={groupRef}>
      {/* Inner core */}
      <mesh ref={innerRef}>
        <sphereGeometry args={[0.5, 32, 32]} />
        <meshBasicMaterial color={color} />
      </mesh>
      {/* Outer glow */}
      <mesh>
        <sphereGeometry args={[0.8, 32, 32]} />
        <meshBasicMaterial color={color} transparent opacity={0.3} />
      </mesh>
      {/* Rotating rings */}
      <group ref={ringsRef}>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[1.2, 0.02, 16, 64]} />
          <meshBasicMaterial color={color} transparent opacity={0.6} />
        </mesh>
        <mesh rotation={[Math.PI / 3, Math.PI / 4, 0]}>
          <torusGeometry args={[1.0, 0.015, 16, 64]} />
          <meshBasicMaterial color={color} transparent opacity={0.4} />
        </mesh>
        <mesh rotation={[Math.PI / 6, -Math.PI / 3, 0]}>
          <torusGeometry args={[1.4, 0.01, 16, 64]} />
          <meshBasicMaterial color={color} transparent opacity={0.3} />
        </mesh>
      </group>
    </group>
  );
}

// Individual network node
function NetworkNodeMesh({
  node,
  primaryColor,
  accentColor,
  activationRef,
}: {
  node: NetworkNode;
  primaryColor: THREE.Color;
  accentColor: THREE.Color;
  activationRef: React.MutableRefObject<Map<number, number>>;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const glowRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    if (!meshRef.current || !glowRef.current) return;
    const time = state.clock.elapsedTime;

    // Get activation level (set by pulses reaching this node)
    const activation = activationRef.current.get(node.id) || 0;

    // Base pulse
    const basePulse = 1 + Math.sin(time * 1.5 + node.pulsePhase) * 0.05;
    // Activation boost
    const activationBoost = 1 + activation * 0.5;

    const scale = 0.15 * basePulse * activationBoost;
    meshRef.current.scale.setScalar(scale);
    glowRef.current.scale.setScalar(scale * 3);

    // Color interpolation based on activation
    const material = meshRef.current.material as THREE.MeshBasicMaterial;
    const targetColor = activation > 0.3 ? accentColor : primaryColor;
    material.color.lerp(targetColor, 0.1);

    // Glow intensity
    const glowMaterial = glowRef.current.material as THREE.MeshBasicMaterial;
    glowMaterial.opacity = 0.15 + activation * 0.4;

    // Decay activation
    if (activation > 0) {
      activationRef.current.set(node.id, Math.max(0, activation - 0.02));
    }
  });

  if (node.isCore) return null;

  return (
    <group position={node.position}>
      <mesh ref={meshRef}>
        <sphereGeometry args={[1, 16, 16]} />
        <meshBasicMaterial color={primaryColor} />
      </mesh>
      <mesh ref={glowRef}>
        <sphereGeometry args={[1, 8, 8]} />
        <meshBasicMaterial color={primaryColor} transparent opacity={0.15} />
      </mesh>
    </group>
  );
}

// Connection lines between nodes
function ConnectionLines({
  nodes,
  primaryColor,
}: {
  nodes: NetworkNode[];
  primaryColor: THREE.Color;
}) {
  const linesRef = useRef<THREE.LineSegments>(null);

  const geometry = useMemo(() => {
    const positions: number[] = [];

    nodes.forEach((node) => {
      node.connections.forEach((targetId) => {
        const target = nodes.find((n) => n.id === targetId);
        if (target && node.id < targetId) {
          // Only draw once per pair
          positions.push(
            node.position.x,
            node.position.y,
            node.position.z,
            target.position.x,
            target.position.y,
            target.position.z
          );
        }
      });
    });

    const geo = new THREE.BufferGeometry();
    geo.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(positions, 3)
    );
    return geo;
  }, [nodes]);

  return (
    <lineSegments ref={linesRef} geometry={geometry}>
      <lineBasicMaterial
        color={primaryColor}
        transparent
        opacity={0.25}
        linewidth={1}
      />
    </lineSegments>
  );
}

// Pulses traveling along connections
function ConnectionPulses({
  nodes,
  pulsesRef,
  primaryColor,
  accentColor,
  activationRef,
}: {
  nodes: NetworkNode[];
  pulsesRef: React.MutableRefObject<Pulse[]>;
  primaryColor: THREE.Color;
  accentColor: THREE.Color;
  activationRef: React.MutableRefObject<Map<number, number>>;
}) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const maxPulses = 50;
  const dummy = useMemo(() => new THREE.Object3D(), []);

  // Build connection lookup
  const connections = useMemo(() => {
    const conns: { from: NetworkNode; to: NetworkNode }[] = [];
    nodes.forEach((node) => {
      node.connections.forEach((targetId) => {
        const target = nodes.find((n) => n.id === targetId);
        if (target) {
          conns.push({ from: node, to: target });
        }
      });
    });
    return conns;
  }, [nodes]);

  useFrame(() => {
    if (!meshRef.current) return;

    const pulses = pulsesRef.current;

    // Update pulse positions
    pulses.forEach((pulse, i) => {
      pulse.progress += pulse.speed * pulse.direction;

      // When pulse reaches end, activate the target node
      if (pulse.progress >= 1 || pulse.progress <= 0) {
        const conn = connections[pulse.connectionIndex];
        if (conn) {
          const targetNode = pulse.direction === 1 ? conn.to : conn.from;
          activationRef.current.set(
            targetNode.id,
            Math.min(1, (activationRef.current.get(targetNode.id) || 0) + 0.5)
          );
        }
        // Reset pulse
        pulse.progress = pulse.direction === 1 ? 0 : 1;
        pulse.connectionIndex = Math.floor(Math.random() * connections.length);
        pulse.direction = Math.random() > 0.5 ? 1 : -1;
        pulse.speed = 0.008 + Math.random() * 0.012;
      }

      // Position the pulse
      const conn = connections[pulse.connectionIndex];
      if (conn && i < maxPulses) {
        const pos = new THREE.Vector3().lerpVectors(
          conn.from.position,
          conn.to.position,
          pulse.progress
        );
        dummy.position.copy(pos);
        dummy.scale.setScalar(0.08);
        dummy.updateMatrix();
        meshRef.current!.setMatrixAt(i, dummy.matrix);

        // Color based on direction
        meshRef.current!.setColorAt(
          i,
          pulse.direction === 1 ? accentColor : primaryColor
        );
      }
    });

    // Hide unused instances
    for (let i = pulses.length; i < maxPulses; i++) {
      dummy.position.set(0, 0, -1000);
      dummy.scale.setScalar(0);
      dummy.updateMatrix();
      meshRef.current.setMatrixAt(i, dummy.matrix);
    }

    meshRef.current.instanceMatrix.needsUpdate = true;
    if (meshRef.current.instanceColor) {
      meshRef.current.instanceColor.needsUpdate = true;
    }
  });

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, maxPulses]}>
      <sphereGeometry args={[1, 8, 8]} />
      <meshBasicMaterial toneMapped={false} />
    </instancedMesh>
  );
}

// Main scene
function Scene({
  nodeCount = 20,
  speed = 1,
  enableGlow = true,
  systemActivity = 0.7,
  primaryColor,
  accentColor,
}: {
  nodeCount: number;
  speed: number;
  enableGlow: boolean;
  systemActivity: number;
  primaryColor: THREE.Color;
  accentColor: THREE.Color;
}) {
  const groupRef = useRef<THREE.Group>(null);
  const activationRef = useRef<Map<number, number>>(new Map());
  const pulsesRef = useRef<Pulse[]>([]);

  // Generate structured network nodes
  const nodes = useMemo<NetworkNode[]>(() => {
    const result: NetworkNode[] = [];
    const rand = seededRandom(42);

    // Core node at center
    result.push({
      id: 0,
      position: new THREE.Vector3(0, 0, 0),
      layer: 0,
      connections: [],
      pulsePhase: 0,
      isCore: true,
    });

    // Inner ring (layer 1) - 6 nodes
    const layer1Count = Math.min(6, nodeCount - 1);
    for (let i = 0; i < layer1Count; i++) {
      const angle = (i / layer1Count) * Math.PI * 2;
      const radius = 3;
      result.push({
        id: result.length,
        position: new THREE.Vector3(
          Math.cos(angle) * radius,
          (rand() - 0.5) * 1,
          Math.sin(angle) * radius
        ),
        layer: 1,
        connections: [0], // Connect to core
        pulsePhase: rand() * Math.PI * 2,
        isCore: false,
      });
    }

    // Middle ring (layer 2) - 10 nodes
    const layer2Count = Math.min(10, Math.max(0, nodeCount - 7));
    for (let i = 0; i < layer2Count; i++) {
      const angle = (i / layer2Count) * Math.PI * 2 + Math.PI / 10;
      const radius = 5.5;
      const nodeId = result.length;

      // Connect to nearest layer 1 nodes
      const nearestLayer1 = result
        .filter((n) => n.layer === 1)
        .sort((a, b) => {
          const posA = new THREE.Vector3(
            Math.cos(angle) * radius,
            0,
            Math.sin(angle) * radius
          );
          return a.position.distanceTo(posA) - b.position.distanceTo(posA);
        })
        .slice(0, 2)
        .map((n) => n.id);

      result.push({
        id: nodeId,
        position: new THREE.Vector3(
          Math.cos(angle) * radius,
          (rand() - 0.5) * 2,
          Math.sin(angle) * radius
        ),
        layer: 2,
        connections: nearestLayer1,
        pulsePhase: rand() * Math.PI * 2,
        isCore: false,
      });
    }

    // Outer ring (layer 3) - remaining nodes
    const layer3Count = Math.max(0, nodeCount - 17);
    for (let i = 0; i < layer3Count; i++) {
      const angle = (i / Math.max(layer3Count, 1)) * Math.PI * 2;
      const radius = 8;
      const nodeId = result.length;

      // Connect to nearest layer 2 nodes
      const nearestLayer2 = result
        .filter((n) => n.layer === 2)
        .sort((a, b) => {
          const posA = new THREE.Vector3(
            Math.cos(angle) * radius,
            0,
            Math.sin(angle) * radius
          );
          return a.position.distanceTo(posA) - b.position.distanceTo(posA);
        })
        .slice(0, 2)
        .map((n) => n.id);

      result.push({
        id: nodeId,
        position: new THREE.Vector3(
          Math.cos(angle) * radius,
          (rand() - 0.5) * 2.5,
          Math.sin(angle) * radius
        ),
        layer: 3,
        connections: nearestLayer2,
        pulsePhase: rand() * Math.PI * 2,
        isCore: false,
      });
    }

    // Update core connections (bidirectional)
    result.forEach((node) => {
      node.connections.forEach((connId) => {
        const target = result.find((n) => n.id === connId);
        if (target && !target.connections.includes(node.id)) {
          target.connections.push(node.id);
        }
      });
    });

    return result;
  }, [nodeCount]);

  // Initialize pulses
  useEffect(() => {
    const pulseCount = Math.floor(15 * systemActivity);
    const connections: number[] = [];

    // Generate connection indices
    let connIndex = 0;
    nodes.forEach((node) => {
      node.connections.forEach((targetId) => {
        if (node.id < targetId) {
          connections.push(connIndex++);
        }
      });
    });

    pulsesRef.current = Array.from({ length: pulseCount }, (_, i) => ({
      connectionIndex: i % Math.max(1, connections.length),
      progress: Math.random(),
      speed: (0.008 + Math.random() * 0.012) * speed,
      direction: Math.random() > 0.5 ? 1 : -1,
    }));
  }, [nodes, systemActivity, speed]);

  // Slow rotation
  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.rotation.y = state.clock.elapsedTime * 0.05 * speed;
    }
  });

  return (
    <>
      <group ref={groupRef}>
        {/* Central core */}
        <CoreNode color={accentColor} />

        {/* Network nodes */}
        {nodes.map((node) => (
          <NetworkNodeMesh
            key={node.id}
            node={node}
            primaryColor={primaryColor}
            accentColor={accentColor}
            activationRef={activationRef}
          />
        ))}

        {/* Connection lines */}
        <ConnectionLines nodes={nodes} primaryColor={primaryColor} />

        {/* Traveling pulses */}
        <ConnectionPulses
          nodes={nodes}
          pulsesRef={pulsesRef}
          primaryColor={primaryColor}
          accentColor={accentColor}
          activationRef={activationRef}
        />
      </group>

      {/* Post-processing */}
      {enableGlow && (
        <EffectComposer>
          <Bloom
            intensity={2}
            luminanceThreshold={0.1}
            luminanceSmoothing={0.9}
            mipmapBlur
          />
        </EffectComposer>
      )}
    </>
  );
}

export function NeuralNetwork({
  className,
  backgroundColor = "transparent",
  primaryColor = DEFAULT_PRIMARY,
  accentColor = DEFAULT_ACCENT,
  nodeCount = 20,
  speed = 1,
  enableGlow = true,
  systemActivity = 0.7,
}: NeuralNetworkProps) {
  const primaryColorObj = useMemo(
    () => new THREE.Color(primaryColor),
    [primaryColor]
  );
  const accentColorObj = useMemo(
    () => new THREE.Color(accentColor),
    [accentColor]
  );

  return (
    <div
      className={className}
      style={{
        width: "100%",
        height: "100%",
        background: backgroundColor,
        position: "relative",
      }}
    >
      <Canvas
        camera={{ position: [0, 5, 12], fov: 60 }}
        gl={{
          antialias: true,
          alpha: true,
          powerPreference: "high-performance",
        }}
        dpr={[1, 2]}
      >
        <Scene
          nodeCount={nodeCount}
          speed={speed}
          enableGlow={enableGlow}
          systemActivity={systemActivity}
          primaryColor={primaryColorObj}
          accentColor={accentColorObj}
        />
      </Canvas>
    </div>
  );
}
