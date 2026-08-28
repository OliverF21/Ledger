import { CloseFooter } from "@/components/CloseFooter";
import { DownloadHonest } from "@/components/DownloadHonest";
import { Glow } from "@/components/Glow";
import { Grain } from "@/components/Grain";
import { HowItWorks } from "@/components/HowItWorks";
import { LocalFirst } from "@/components/LocalFirst";
import { Nav } from "@/components/Nav";
import { ProductWalk } from "@/components/ProductWalk";
import { ScrollRefresh } from "@/components/ScrollRefresh";
import { getLatestRelease } from "@/release/github";

export default async function Home() {
  const release = await getLatestRelease();

  return (
    <>
      <ScrollRefresh />
      <Glow />
      <Grain />
      <div className="relative z-[1]">
        <Nav />
        <main>
          <ProductWalk release={release} />
          <LocalFirst />
          <HowItWorks />
          <DownloadHonest release={release} />
        </main>
        <CloseFooter release={release} />
      </div>
    </>
  );
}
