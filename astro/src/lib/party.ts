export function getPartyFromDesignation(designation: string | null | undefined): string | null {
  if (designation?.includes('Workers')) return 'WP';
  if (designation?.includes('Progress')) return 'PSP';
  if (designation?.includes('Minister') || designation?.includes('Secretary')) return 'PAP';
  return null;
}
