import { DashboardSidebar } from "@/components/DashboardSidebar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen bg-background">
      <DashboardSidebar />
      <main className="flex min-h-0 flex-1 flex-col overflow-y-auto overflow-x-hidden px-8 py-6">{children}</main>
    </div>
  );
}
