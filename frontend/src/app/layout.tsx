import type { Metadata } from 'next';
import './globals.css';
import { UserStoreProvider } from '@/lib/store/userStore';
import { UIStoreProvider } from '@/lib/store/uiStore';
import ToastContainer from '@/components/ui/ToastContainer';

export const metadata: Metadata = {
  title: 'Career Coach — AI-Powered Career Acceleration',
  description:
    'Upload your CV, get AI-powered job recommendations, track applications, and access tailored application materials — all in one platform.',
  keywords: ['career', 'job matching', 'AI', 'CV', 'recommendations', 'career coach'],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Sora:wght@600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <UserStoreProvider>
          <UIStoreProvider>
            {children}
            <ToastContainer />
          </UIStoreProvider>
        </UserStoreProvider>
      </body>
    </html>
  );
}
