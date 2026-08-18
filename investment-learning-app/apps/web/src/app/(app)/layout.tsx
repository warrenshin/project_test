import { ProtectedPage } from "@/components/ProtectedPage";
import { TabBar } from "@/components/TabBar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedPage>
      <main className="page">{children}</main>
      <TabBar />
    </ProtectedPage>
  );
}
