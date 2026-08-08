import AdminRealtimePresenceScreen from "../../../components/admin-realtime-presence-screen";
import { normalizeUiLanguage } from "../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

export default function AdminRealtimePage({ searchParams }: { searchParams: SearchParams }): JSX.Element {
  const language = normalizeUiLanguage(Array.isArray(searchParams.lang) ? searchParams.lang[0] : searchParams.lang);
  return <AdminRealtimePresenceScreen language={language} />;
}
