/** Static demonstration mode: a pre-rendered build (GitHub Pages) with no backend at all. */
export const isStaticDemo = (): boolean => import.meta.env?.VITE_STATIC_DEMO === "true";

/** Where the pre-computed fixtures live, honouring the Vite `base` (e.g. /IncidentLens/). */
export const demoDataUrl = (file: string): string => {
  const base = (import.meta.env?.BASE_URL as string | undefined) ?? "/";
  return `${base.endsWith("/") ? base : `${base}/`}demo-data/${file}`;
};

export const REPO_URL = "https://github.com/badmrfrosty313/IncidentLens";
