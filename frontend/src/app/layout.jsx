import './globals.css';

export const metadata = {
  title: 'CareFlow',
  description: 'A calm, connected workspace for clinic teams and patients.',
};

export default function RootLayout({ children }) {
  return <html lang="en"><body>{children}</body></html>;
}
