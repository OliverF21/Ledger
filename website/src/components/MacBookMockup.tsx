"use client";

import Image from "next/image";
import { useEffect, useMemo, useRef } from "react";
import type { MutableRefObject } from "react";
import { site } from "@/content/site";
import { walkFrame } from "@/components/walkProgress";

const scenes = site.features.scenes;

function smoothstep(t: number) {
  const x = Math.min(1, Math.max(0, t));
  return x * x * (3 - 2 * x);
}

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

export function MacBookMockup({
  progressRef,
  freeze,
}: {
  progressRef: MutableRefObject<number>;
  freeze: boolean;
}) {
  const rigRef = useRef<HTMLDivElement>(null);
  const layerRefs = useRef<(HTMLDivElement | null)[]>([]);

  const shots = useMemo(
    () => scenes.map((scene) => site.shots[scene.shot]),
    [],
  );

  useEffect(() => {
    if (freeze) return;

    let frame = 0;

    const tick = () => {
      const progress = progressRef.current;
      const eased = smoothstep(progress);
      const { scene, blend } = walkFrame(progress);
      const next = Math.min(scenes.length - 1, scene + 1);

      for (let i = 0; i < layerRefs.current.length; i += 1) {
        const layer = layerRefs.current[i];
        if (!layer) continue;

        let opacity = 0;
        if (scene >= scenes.length - 1) {
          opacity = i === scene ? 1 : 0;
        } else if (i === scene) {
          opacity = 1 - blend;
        } else if (i === next) {
          opacity = blend;
        }

        layer.style.opacity = String(opacity);
      }

      const rig = rigRef.current;
      if (rig) {
        rig.style.transform = [
          "perspective(1600px)",
          `rotateY(${lerp(-14, -4, eased)}deg)`,
          `rotateX(${lerp(5, 1.5, eased)}deg)`,
          `translateY(${lerp(0, -6, eased)}px)`,
          `scale(${lerp(1, 1.02, eased)})`,
        ].join(" ");
      }

      frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [freeze, progressRef]);

  return (
    <div className="macbook-mockup" aria-hidden={freeze}>
      <div ref={rigRef} className="macbook-mockup__rig">
        <div className="macbook-mockup__device">
          <Image
            src={site.shots.macbook}
            alt=""
            width={2400}
            height={1600}
            priority
            sizes="(min-width: 1024px) 58vw, 100vw"
            className="macbook-mockup__frame"
          />

          <div className="macbook-mockup__screen">
            {shots.map((src, index) => (
              <div
                key={src}
                ref={(node) => {
                  layerRefs.current[index] = node;
                }}
                className="macbook-mockup__layer"
                style={{ opacity: freeze ? (index === 0 ? 1 : 0) : index === 0 ? 1 : 0 }}
              >
                <Image
                  src={src}
                  alt=""
                  fill
                  sizes="(min-width: 1024px) 42vw, 88vw"
                  className="macbook-mockup__shot"
                />
              </div>
            ))}
            <div className="macbook-mockup__notch" aria-hidden="true" />
          </div>
        </div>
      </div>
    </div>
  );
}
