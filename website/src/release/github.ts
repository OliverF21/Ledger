export type LatestRelease = {
  tag: string | null;
  macDmg: string | null;
  winExe: string | null;
  htmlUrl: string;
};

const FALLBACK: LatestRelease = {
  tag: null,
  macDmg: null,
  winExe: null,
  htmlUrl: "https://github.com/OliverF21/Ledger/releases/latest",
};

type GithubAsset = {
  name: string;
  browser_download_url: string;
};

type GithubRelease = {
  tag_name?: string;
  html_url?: string;
  assets?: GithubAsset[];
};

export async function getLatestRelease(): Promise<LatestRelease> {
  try {
    const res = await fetch(
      "https://api.github.com/repos/OliverF21/Ledger/releases/latest",
      {
        next: { revalidate: 3600 },
        headers: {
          Accept: "application/vnd.github+json",
          "User-Agent": "ledger-website",
        },
      },
    );
    if (!res.ok) return FALLBACK;

    const data = (await res.json()) as GithubRelease;
    const assets = data.assets ?? [];

    const macDmg =
      assets.find((a) => a.name.endsWith(".dmg") && !a.name.endsWith(".sig"))
        ?.browser_download_url ?? null;

    const winExe =
      assets.find(
        (a) => a.name.includes("x64-setup.exe") && !a.name.endsWith(".sig"),
      )?.browser_download_url ?? null;

    return {
      tag: data.tag_name ?? null,
      macDmg,
      winExe,
      htmlUrl: data.html_url ?? FALLBACK.htmlUrl,
    };
  } catch {
    return FALLBACK;
  }
}
