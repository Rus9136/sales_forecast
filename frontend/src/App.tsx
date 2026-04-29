import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppLayout } from '@/components/layout/app-layout'
import { DepartmentsPage } from '@/pages/departments-page'
import { EmployeesPage } from '@/pages/employees-page'
import { DailySalesPage } from '@/pages/daily-sales-page'
import { HourlySalesPage } from '@/pages/hourly-sales-page'
import { WaiterSalesPage } from '@/pages/waiter-sales-page'
import { ForecastBranchPage } from '@/pages/forecast-branch-page'
import { ForecastComparisonPage } from '@/pages/forecast-comparison-page'
import { SyncPage } from '@/pages/sync-page'
import { BonusCalculationsPage } from '@/pages/bonus-calculations-page'
import { BonusSchemesPage } from '@/pages/bonus-schemes-page'
import { BonusManualKpiPage } from '@/pages/bonus-manual-kpi-page'
import { BonusMonthlyPlansPage } from '@/pages/bonus-monthly-plans-page'

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
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<Navigate to="/departments" replace />} />
            <Route path="/departments" element={<DepartmentsPage />} />
            <Route path="/employees" element={<EmployeesPage />} />
            <Route path="/sales/daily" element={<DailySalesPage />} />
            <Route path="/sales/hourly" element={<HourlySalesPage />} />
            <Route path="/sales/waiters" element={<WaiterSalesPage />} />
            <Route path="/forecast/branches" element={<ForecastBranchPage />} />
            <Route path="/forecast/comparison" element={<ForecastComparisonPage />} />
            <Route path="/sync" element={<SyncPage />} />
            <Route path="/bonus/calculations" element={<BonusCalculationsPage />} />
            <Route path="/bonus/schemes" element={<BonusSchemesPage />} />
            <Route path="/bonus/manual-kpi" element={<BonusManualKpiPage />} />
            <Route path="/bonus/monthly-plans" element={<BonusMonthlyPlansPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
