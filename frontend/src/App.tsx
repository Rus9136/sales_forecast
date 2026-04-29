import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppLayout } from '@/components/layout/app-layout'
import { DepartmentsPage } from '@/pages/departments-page'
import { DailySalesPage } from '@/pages/daily-sales-page'
import { HourlySalesPage } from '@/pages/hourly-sales-page'
import { ForecastBranchPage } from '@/pages/forecast-branch-page'
import { ForecastComparisonPage } from '@/pages/forecast-comparison-page'
import { SyncPage } from '@/pages/sync-page'

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
            <Route path="/sales/daily" element={<DailySalesPage />} />
            <Route path="/sales/hourly" element={<HourlySalesPage />} />
            <Route path="/forecast/branches" element={<ForecastBranchPage />} />
            <Route path="/forecast/comparison" element={<ForecastComparisonPage />} />
            <Route path="/sync" element={<SyncPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
