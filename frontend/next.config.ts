import type { NextConfig } from "next";

// Exportación estática: el perfil de arquitectura de LF sirve el front desde S3 + CloudFront.
const nextConfig: NextConfig = {
  output: "export",
};

export default nextConfig;
