# A1: interpretación del texto libre (candidato)

Objetivo: transformar una solicitud literal y el contexto existente en una propuesta de REQUEST_CONTEXT_V1, sin perder información.

Entrada: original_request, business, request_identity, target_hints, source_refs, provided_facts, constraints, ambiguities.

Reglas:
1. Conservar el texto original y el hash.
2. Extraer las acciones solicitadas sin agregar otras; una solicitud de evaluar e implementar contiene dos acciones.
3. Aprovechar códigos y nombres ya presentes en el contexto. Conservar la referencia de procedencia; A1 no verifica existencia o vigencia.
4. Cuando una corrección tipográfica sea ambigua y material, expresarla como duda.
5. Mantener separados los límites de gobernanza y las restricciones que realmente indicó el usuario.
6. No decidir tipo de cambio, estrategia, código ni fuente vigente. A2 y A3 tienen esas responsabilidades.
7. Entregar la interpretación al validador tipado de A1.

La guarda Python verifica estructura y preservación de datos, no significado. La fidelidad al texto original requiere un juez semántico independiente aún no integrado.

Resultado de entrada semántica: REQUIRES_SEMANTIC_REVIEW y next_capability=null. No habilita A2 sin revisión.
