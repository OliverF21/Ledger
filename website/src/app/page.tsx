import { CloseFooter } from "@/components/CloseFooter";
import { DownloadHonest } from "@/components/DownloadHonest";
import { FeatureBento } from "@/components/FeatureBento";
import { Glow } from "@/components/Glow";
import { Grain } from "@/components/Grain";
import { Hero } from "@/components/Hero";
import { HowItWorks } from "@/components/HowItWorks";
import { LocalFirst } from "@/components/LocalFirst";
import { Nav } from "@/components/Nav";
import { getLatestRelease } from "@/release/github";

export default async function Home() {
  const release = await getLatestRelease();

  return (
    <>
      <Glow />
      <Grain />
      <div className="relative z-[1]">
        <Nav />
        <main>
          <Hero release={release} />
          <LocalFirst />
          <FeatureBento />
          <HowItWorks />
          <DownloadHonest release={release} />
        </main>
        <CloseFooter release={release} />
      </div>
    </>
  );
}
