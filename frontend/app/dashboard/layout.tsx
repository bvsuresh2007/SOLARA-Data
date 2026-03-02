import { UserMenu } from "@/components/user-menu";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      {/* Top bar with user menu */}
      <div className="flex items-center justify-end px-6 pt-4">
        <UserMenu />
      </div>
      {children}
    </div>
  );
}
