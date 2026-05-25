import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppLayout } from '@/components/layout/app-layout'
import { AuthProvider } from '@/contexts/auth-context'
import { UIPrefsProvider } from '@/contexts/ui-prefs-context'
import { ProtectedRoute } from '@/components/auth/protected-route'
import { HomeRedirect } from '@/components/auth/home-redirect'
import { LoginPage } from '@/pages/login-page'
import { ForbiddenPage } from '@/pages/forbidden-page'
import { DashboardPage } from '@/pages/dashboard-page'
import { DepartmentsPage } from '@/pages/departments-page'
import { EmployeesPage } from '@/pages/employees-page'
import { DailySalesPage } from '@/pages/daily-sales-page'
import { HourlySalesPage } from '@/pages/hourly-sales-page'
import { WaiterSalesPage } from '@/pages/waiter-sales-page'
import { ForecastBranchPage } from '@/pages/forecast-branch-page'
import { ForecastComparisonPage } from '@/pages/forecast-comparison-page'
import { SkuForecastPage } from '@/pages/sku-forecast-page'
import { SyncPage } from '@/pages/sync-page'
import { AIRecommendationsPage } from '@/pages/ai-recommendations-page'
import { MenuProductsPage } from '@/pages/menu/products-page'
import { MenuGroupsPage } from '@/pages/menu/groups-page'
import { ReceiptsPage } from '@/pages/receipts/receipts-page'
import { StatsByProductPage } from '@/pages/receipts/stats-by-product-page'
import { UsersPage } from '@/pages/users-page'
import { RolesPage } from '@/pages/roles-page'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <UIPrefsProvider>
        <BrowserRouter>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route element={<ProtectedRoute />}>
                <Route element={<AppLayout />}>
                  <Route path="/" element={<HomeRedirect />} />
                  <Route path="/forbidden" element={<ForbiddenPage />} />
                  <Route element={<ProtectedRoute section="dashboard" />}>
                    <Route path="/dashboard" element={<DashboardPage />} />
                  </Route>
                  <Route element={<ProtectedRoute section="departments" />}>
                    <Route path="/departments" element={<DepartmentsPage />} />
                  </Route>
                  <Route element={<ProtectedRoute section="employees" />}>
                    <Route path="/employees" element={<EmployeesPage />} />
                  </Route>
                  <Route element={<ProtectedRoute section="sales.daily" />}>
                    <Route path="/sales/daily" element={<DailySalesPage />} />
                  </Route>
                  <Route element={<ProtectedRoute section="sales.hourly" />}>
                    <Route path="/sales/hourly" element={<HourlySalesPage />} />
                  </Route>
                  <Route element={<ProtectedRoute section="sales.waiters" />}>
                    <Route path="/sales/waiters" element={<WaiterSalesPage />} />
                  </Route>
                  <Route element={<ProtectedRoute section="forecast.branches" />}>
                    <Route path="/forecast/branches" element={<ForecastBranchPage />} />
                  </Route>
                  <Route element={<ProtectedRoute section="forecast.comparison" />}>
                    <Route path="/forecast/comparison" element={<ForecastComparisonPage />} />
                  </Route>
                  <Route element={<ProtectedRoute section="forecast.sku" />}>
                    <Route path="/forecast/sku" element={<SkuForecastPage />} />
                  </Route>
                  <Route element={<ProtectedRoute section="sync" />}>
                    <Route path="/sync" element={<SyncPage />} />
                  </Route>
                  <Route element={<ProtectedRoute section="ai.recommendations" />}>
                    <Route path="/ai-recommendations" element={<AIRecommendationsPage />} />
                  </Route>
                  <Route element={<ProtectedRoute section="menu.products" />}>
                    <Route path="/menu/products" element={<MenuProductsPage />} />
                  </Route>
                  <Route element={<ProtectedRoute section="menu.groups" />}>
                    <Route path="/menu/groups" element={<MenuGroupsPage />} />
                  </Route>
                  <Route element={<ProtectedRoute section="receipts.list" />}>
                    <Route path="/receipts" element={<ReceiptsPage />} />
                  </Route>
                  <Route element={<ProtectedRoute section="receipts.stats" />}>
                    <Route path="/receipts/stats" element={<StatsByProductPage />} />
                  </Route>
                  <Route element={<ProtectedRoute section="users" />}>
                    <Route path="/users" element={<UsersPage />} />
                  </Route>
                  <Route element={<ProtectedRoute section="roles" />}>
                    <Route path="/roles" element={<RolesPage />} />
                  </Route>
                </Route>
              </Route>
            </Routes>
          </AuthProvider>
        </BrowserRouter>
      </UIPrefsProvider>
    </QueryClientProvider>
  )
}
