# LF pinned stack skills / CANDIDATE_SANDBOX_ONLY
Standards source: paulozterra/lf-programming-sandbox@f18b2d96b7e1a8263749d35a7afcc9c043521cb8:standards/catalog.json
Catalog SHA-256: 26ca9cf9936ef01b50f9af504e4a9b796ee7d7d538d5724ff388c9fb90e8ddb3

## NEXTJS@0.2.0 priority 1
# Next.js — skill L2

## Propósito
Procedimiento genérico por stack; el catálogo se resuelve por el pin del pedido.

## Entradas
Stack verificado, dominios PG-02, pin PG-01, contrato Fase 1 y manifiesto de arquitectura separados.

## Orden de trabajo
Verificar tipos/cliente API generados y contratos antes de modificar componentes. Ejecutar los checks declarados.

## Verificación
Resolver `check_set_ref` mediante la fuente única de checks. Mantener estados blocking y shadow.

## Salida
Paquete de evidencias, comandos ejecutados y recibo de ensamblado; nunca autodeclarar GO.


### Literal PG00 STD-FE rules
- STD-FE-01 [APROBADO]: Componentes y tipos en PascalCase; hooks `useX`; variables y funciones en camelCase; constantes en UPPER_SNAKE; sin prefijo `I` en interfaces. Excepción: las propiedades de los tipos generados de la API se mantienen en snake_case (D3)
- STD-FE-02 [APROBADO]: Todos los archivos en kebab-case (`b2b-shell.tsx`, `client-session.ts`), como ya usa `libertad-financiera`; el componente dentro del archivo sigue en PascalCase
- STD-FE-03 [APROBADO]: TypeScript `strict`, sin `any` implícito ni `@ts-ignore` sin waiver
- STD-FE-04 [APROBADO]: Llamadas a la API solo con el cliente o los tipos generados (`api-client` desde OpenAPI, o `supabase gen types`); nada de `fetch` a mano
- STD-FE-05 [APROBADO]: El FE no recalcula precios ni montos
- STD-FE-06 [APROBADO]: Accesibilidad, responsive y Core Web Vitals
- STD-FE-07 [APROBADO]: Formato
