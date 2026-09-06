// Shared types for the QA/One API surface. Mirrors services/api schemas.
// Origin is the attribution-registry row; each is one of the 41 projects
// whose ideas the platform merges.

export interface Origin {
  rank: number;
  name: string;
  project: string;
  one_liner: string;
  repo: string;
  live: string | null;
  tags: string[];
  note: string | null;
}

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
