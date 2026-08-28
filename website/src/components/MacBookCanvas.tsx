"use client";

import { Suspense, useLayoutEffect, useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import {
  ContactShadows,
  Environment,
  Lightformer,
  RoundedBox,
  useTexture,
} from "@react-three/drei";
import * as THREE from "three";
import type { MutableRefObject } from "react";
import { site } from "@/content/site";

const scenes = site.features.scenes;
const SCREEN_PATHS = scenes.map((s) => site.shots[s.shot]);

const aluminum = {
  metalness: 0.9,
  roughness: 0.38,
  clearcoat: 0.35,
  clearcoatRoughness: 0.4,
} as const;

type Pose = {
  yaw: number;
  pitch: number;
  roll: number;
  lid: number;
};

function poseAt(progress: number): Pose {
  const t = THREE.MathUtils.clamp(progress, 0, 1);
  const e = t * t * (3 - 2 * t);
  return {
    yaw: THREE.MathUtils.lerp(-0.52, -0.1, e),
    pitch: THREE.MathUtils.lerp(0.16, 0.04, e),
    roll: THREE.MathUtils.lerp(-0.035, 0, e),
    lid: THREE.MathUtils.lerp(-0.2, -0.08, e),
  };
}

function Screen({ active }: { active: number }) {
  const maps = useTexture(SCREEN_PATHS) as THREE.Texture[];

  useLayoutEffect(() => {
    for (const tex of maps) {
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = 8;
      tex.needsUpdate = true;
    }
  }, [maps]);

  return (
    <group>
      {maps.map((tex, i) => (
        <mesh key={scenes[i].key} position={[0, 0, i === active ? 0.001 : 0]} renderOrder={2}>
          <planeGeometry args={[13.28, 8.28]} />
          <meshBasicMaterial
            map={tex}
            toneMapped={false}
            transparent
            opacity={i === active ? 1 : 0}
          />
        </mesh>
      ))}
    </group>
  );
}

function Deck() {
  const map = useTexture(site.shots.deck);

  useLayoutEffect(() => {
    map.colorSpace = THREE.SRGBColorSpace;
    map.anisotropy = 8;
    map.needsUpdate = true;
  }, [map]);

  return (
    <mesh rotation-x={-Math.PI / 2} position={[0, 0.385, 0.12]} renderOrder={1}>
      <planeGeometry args={[13.55, 8.55]} />
      <meshBasicMaterial map={map} toneMapped={false} />
    </mesh>
  );
}

function LaptopBody({
  active,
  progressRef,
  freeze,
}: {
  active: number;
  progressRef: MutableRefObject<number>;
  freeze: boolean;
}) {
  const rig = useRef<THREE.Group>(null);
  const lid = useRef<THREE.Group>(null);
  const rest = useMemo(() => poseAt(freeze ? 1 : 0), [freeze]);

  useFrame(() => {
    if (!rig.current || !lid.current) return;
    const next = freeze ? rest : poseAt(progressRef.current);
    rig.current.rotation.y = next.yaw;
    rig.current.rotation.x = next.pitch;
    rig.current.rotation.z = next.roll;
    lid.current.rotation.x = next.lid;
  });

  return (
    <group
      ref={rig}
      position={[0, 0.2, 0]}
      rotation={[rest.pitch, rest.yaw, rest.roll]}
      scale={0.92}
    >
      <RoundedBox args={[14.42, 0.36, 9.96]} radius={0.09} smoothness={6} position={[0, 0.18, 0]}>
        <meshPhysicalMaterial color="#6e727a" {...aluminum} />
      </RoundedBox>
      <RoundedBox args={[14.42, 0.1, 0.42]} radius={0.04} smoothness={4} position={[0, 0.14, 4.86]}>
        <meshPhysicalMaterial color="#868a92" {...aluminum} roughness={0.22} />
      </RoundedBox>
      <mesh position={[0, 0.2, 5.05]}>
        <boxGeometry args={[1.7, 0.05, 0.16]} />
        <meshStandardMaterial color="#16181c" roughness={0.7} />
      </mesh>
      <Suspense fallback={null}>
        <Deck />
      </Suspense>

      <mesh rotation={[0, 0, Math.PI / 2]} position={[0, 0.4, -4.86]}>
        <cylinderGeometry args={[0.085, 0.085, 13.5, 20]} />
        <meshPhysicalMaterial color="#4e5258" {...aluminum} roughness={0.2} />
      </mesh>

      <group ref={lid} position={[0, 0.42, -4.86]} rotation-x={rest.lid}>
        <RoundedBox args={[14.42, 9.28, 0.13]} radius={0.09} smoothness={6} position={[0, 4.64, 0]}>
          <meshPhysicalMaterial color="#5d6168" {...aluminum} />
        </RoundedBox>
        <mesh position={[0, 4.56, 0.068]}>
          <planeGeometry args={[13.95, 8.9]} />
          <meshStandardMaterial color="#090a0c" roughness={0.85} />
        </mesh>
        <group position={[0, 4.42, 0.075]}>
          <Suspense fallback={null}>
            <Screen active={active} />
          </Suspense>
        </group>
        <mesh position={[0, 8.68, 0.08]}>
          <boxGeometry args={[1.12, 0.26, 0.03]} />
          <meshStandardMaterial color="#050608" />
        </mesh>
        <mesh position={[0, 8.68, 0.1]}>
          <circleGeometry args={[0.04, 20]} />
          <meshStandardMaterial color="#142032" emissive="#0b1a28" emissiveIntensity={0.4} />
        </mesh>
      </group>
    </group>
  );
}

function Lights() {
  return (
    <>
      <hemisphereLight args={["#c5d2e6", "#0a0c10", 0.55]} />
      <spotLight
        position={[6, 11, 8]}
        angle={0.55}
        penumbra={1}
        intensity={1.35}
        color="#eef2f7"
      />
      <spotLight
        position={[-6.5, 5, 6]}
        angle={0.75}
        penumbra={1}
        intensity={0.45}
        color="#8eadd8"
      />
      <directionalLight position={[2, 4, -7]} intensity={0.35} color="#d5dde8" />
      <Environment resolution={256}>
        <Lightformer intensity={1.2} position={[0, 5, -2]} scale={[12, 2.4, 1]} />
        <Lightformer intensity={0.7} position={[6, 2, 4]} scale={[4, 6, 1]} />
        <Lightformer intensity={0.55} position={[-6, 1.5, 2]} scale={[3, 5, 1]} color="#9bb6dc" />
        <Lightformer intensity={0.35} position={[0, -2, 4]} scale={[10, 1, 1]} color="#1b2230" />
      </Environment>
    </>
  );
}

export function MacBookCanvas({
  active,
  progressRef,
  freeze,
}: {
  active: number;
  progressRef: MutableRefObject<number>;
  freeze: boolean;
}) {
  return (
    <Canvas
      className="macbook-3d-canvas"
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      dpr={[1, 1.75]}
      camera={{ fov: 32, position: [0, 4.6, 26], near: 0.1, far: 80 }}
      frameloop={freeze ? "demand" : "always"}
      onCreated={({ camera, gl }) => {
        camera.lookAt(0, 2.15, 0);
        gl.toneMapping = THREE.ACESFilmicToneMapping;
        gl.toneMappingExposure = 0.88;
        gl.setClearColor(0x000000, 0);
      }}
    >
      <Lights />
      <LaptopBody active={active} progressRef={progressRef} freeze={freeze} />
      <ContactShadows
        position={[0, 0, 0]}
        opacity={0.48}
        scale={26}
        blur={2.6}
        far={9}
        color="#000000"
      />
    </Canvas>
  );
}
