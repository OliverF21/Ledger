"use client";

import { Suspense, useLayoutEffect, useMemo, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
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
import { walkFrame } from "@/components/walkProgress";

const scenes = site.features.scenes;

const aluminum = {
  metalness: 0.82,
  roughness: 0.42,
  clearcoat: 0.45,
  clearcoatRoughness: 0.35,
} as const;

const SCREEN_Y = 4.88;

type Pose = {
  yaw: number;
  pitch: number;
  roll: number;
  lid: number;
};

function smooth(progress: number) {
  const t = THREE.MathUtils.clamp(progress, 0, 1);
  return t * t * (3 - 2 * t);
}

/** Balanced 3/4 angle: screen readable, chassis still visible. */
function poseAt(progress: number): Pose {
  const e = smooth(progress);
  return {
    yaw: THREE.MathUtils.lerp(-0.28, -0.06, e),
    pitch: THREE.MathUtils.lerp(0.24, 0.1, e),
    roll: THREE.MathUtils.lerp(-0.02, 0, e),
    lid: THREE.MathUtils.lerp(-0.11, -0.06, e),
  };
}

function CameraRig({
  progressRef,
  freeze,
}: {
  progressRef: MutableRefObject<number>;
  freeze: boolean;
}) {
  const { camera } = useThree();

  useFrame(() => {
    const e = smooth(freeze ? 1 : progressRef.current);
    const cam = camera as THREE.PerspectiveCamera;
    cam.position.set(
      0,
      THREE.MathUtils.lerp(5.05, 4.82, e),
      THREE.MathUtils.lerp(16.8, 18.8, e),
    );
    cam.fov = THREE.MathUtils.lerp(24, 26, e);
    cam.lookAt(0, THREE.MathUtils.lerp(SCREEN_Y, 4.78, e), 0);
    cam.updateProjectionMatrix();
  });

  return null;
}

function Screen({ progressRef }: { progressRef: MutableRefObject<number> }) {
  const overview = useTexture(site.shots.overview);
  const transactions = useTexture(site.shots.transactions);
  const budgets = useTexture(site.shots.budgets);
  const investments = useTexture(site.shots.investments);
  const advisor = useTexture(site.shots.advisor);

  const textures = useMemo(
    () => [overview, transactions, budgets, investments, advisor],
    [overview, transactions, budgets, investments, advisor],
  );

  const frontMat = useRef<THREE.MeshBasicMaterial>(null);
  const backMat = useRef<THREE.MeshBasicMaterial>(null);

  useLayoutEffect(() => {
    for (const tex of textures) {
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = 16;
      tex.minFilter = THREE.LinearFilter;
      tex.magFilter = THREE.LinearFilter;
      tex.needsUpdate = true;
    }
  }, [textures]);

  useFrame(() => {
    const { scene, blend } = walkFrame(progressRef.current);
    const next = Math.min(scenes.length - 1, scene + 1);
    const front = frontMat.current;
    const back = backMat.current;
    if (!front || !back) return;

    if (scene >= scenes.length - 1 || blend < 0.001) {
      front.map = textures[scene];
      front.opacity = 1;
      back.opacity = 0;
      return;
    }

    front.map = textures[scene];
    front.opacity = 1 - blend;
    back.map = textures[next];
    back.opacity = blend;
  });

  return (
    <group>
      <mesh renderOrder={1}>
        <planeGeometry args={[13.28, 8.28]} />
        <meshBasicMaterial ref={backMat} toneMapped={false} transparent opacity={0} />
      </mesh>
      <mesh position={[0, 0, 0.001]} renderOrder={2}>
        <planeGeometry args={[13.28, 8.28]} />
        <meshBasicMaterial
          ref={frontMat}
          map={textures[0]}
          toneMapped={false}
          transparent
          opacity={1}
        />
      </mesh>
    </group>
  );
}

function LaptopBody({
  progressRef,
  freeze,
}: {
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
      position={[0, 0.08, 0]}
      rotation={[rest.pitch, rest.yaw, rest.roll]}
      scale={1.02}
    >
      {/* Minimal base — no keyboard texture, keeps focus on the display */}
      <RoundedBox
        args={[14.1, 0.28, 9.6]}
        radius={0.08}
        smoothness={8}
        position={[0, 0.14, 0.35]}
      >
        <meshPhysicalMaterial color="#3a3d44" {...aluminum} roughness={0.55} />
      </RoundedBox>

      <mesh rotation={[0, 0, Math.PI / 2]} position={[0, 0.36, -4.72]}>
        <cylinderGeometry args={[0.07, 0.07, 13.2, 24]} />
        <meshPhysicalMaterial color="#454850" {...aluminum} roughness={0.28} />
      </mesh>

      <group ref={lid} position={[0, 0.36, -4.72]} rotation-x={rest.lid}>
        <RoundedBox
          args={[14.1, 9.1, 0.11]}
          radius={0.08}
          smoothness={8}
          position={[0, 4.55, 0]}
        >
          <meshPhysicalMaterial color="#52565e" {...aluminum} />
        </RoundedBox>
        <mesh position={[0, 4.48, 0.058]}>
          <planeGeometry args={[13.72, 8.72]} />
          <meshStandardMaterial color="#07080a" roughness={0.92} metalness={0.05} />
        </mesh>
        <group position={[0, 4.34, 0.064]}>
          <Suspense fallback={null}>
            <Screen progressRef={progressRef} />
          </Suspense>
        </group>
        <mesh position={[0, 8.56, 0.066]}>
          <boxGeometry args={[0.95, 0.2, 0.025]} />
          <meshStandardMaterial color="#040506" roughness={0.95} />
        </mesh>
      </group>
    </group>
  );
}

function Lights() {
  return (
    <>
      <ambientLight intensity={0.35} color="#b8c4d8" />
      <hemisphereLight args={["#d8e2f0", "#0a0c10", 0.45]} />
      <directionalLight position={[4, 8, 6]} intensity={0.55} color="#eef2f8" />
      <directionalLight position={[-5, 4, 3]} intensity={0.22} color="#9eb8dc" />
      <Environment resolution={512}>
        <Lightformer intensity={0.9} position={[0, 6, 2]} scale={[14, 3, 1]} />
        <Lightformer intensity={0.5} position={[5, 2, 5]} scale={[5, 5, 1]} />
        <Lightformer intensity={0.35} position={[-4, 1, 3]} scale={[4, 4, 1]} color="#a8bce0" />
      </Environment>
    </>
  );
}

export function MacBookCanvas({
  progressRef,
  freeze,
}: {
  progressRef: MutableRefObject<number>;
  freeze: boolean;
}) {
  return (
    <Canvas
      className="macbook-3d-canvas"
      gl={{
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
        stencil: false,
      }}
      dpr={[1, 2]}
      camera={{ fov: 24, position: [0, 5.05, 16.8], near: 0.1, far: 80 }}
      frameloop={freeze ? "demand" : "always"}
      onCreated={({ camera, gl }) => {
        camera.lookAt(0, SCREEN_Y, 0);
        gl.toneMapping = THREE.ACESFilmicToneMapping;
        gl.toneMappingExposure = 0.92;
        gl.setClearColor(0x000000, 0);
      }}
    >
      <CameraRig progressRef={progressRef} freeze={freeze} />
      <Lights />
      <LaptopBody progressRef={progressRef} freeze={freeze} />
      <ContactShadows
        position={[0, 0, 0]}
        opacity={0.32}
        scale={22}
        blur={2.8}
        far={8}
        color="#000000"
      />
    </Canvas>
  );
}
