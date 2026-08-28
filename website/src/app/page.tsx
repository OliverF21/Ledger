import { CloseFooter } from "@/components/CloseFooter";
import { DownloadHonest } from "@/components/DownloadHonest";
import { FeatureBento } from "@/components/FeatureBento";
import { Glow } from "@/components/Glow";
import { Hero } from "@/components/Hero";
import { HowItWorks } from "@/components/HowItWorks";
import { LocalFirst } from "@/components/LocalFirst";
import { Nav } from "@/components/Nav";
import { ProductFrame } from "@/components/ProductFrame";
import { getLatestRelease } from "@/release/github";

export default async function Home() {
  const release = await getLatestRelease();

  return (
    <>
      <Glow />
      <div className="relative z-[1]">
        <Nav />
        <main>
          <Hero release={release} />
          <LocalFirst />
          <ProductFrame />
          <FeatureBento />
          <HowItWorks />
          <DownloadHonest release={release} />
        </main>
        <CloseFooter release={release} />
      </div>
    </>
  );
}
