import { apiClient, unwrap } from './client';
import type { ArtifactContent } from './types';

export async function getArtifact(
  artifactId: string,
  offset = 0,
  limit = 8000,
): Promise<ArtifactContent> {
  return unwrap(
    apiClient.get<{ data: ArtifactContent }>(`/artifacts/${artifactId}`, {
      params: { offset, limit },
    }),
  );
}
