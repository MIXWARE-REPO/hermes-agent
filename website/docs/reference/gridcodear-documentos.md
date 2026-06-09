# Gridcodear Documentos

`gridcodear-documentos` es la skill canónica de Grid Code para transformar cualquier documento en un PDF corporativo con el mismo estilo visual, el mismo contrato de paginación y la misma lógica operativa, sea el contenido técnico, administrativo o comercial.

## Propósito

Esta skill unifica el flujo de generación de documentos Grid Code bajo una sola lógica de producción:

- documentos técnicos: diagnósticos, anomalías, OCPP, DLM, CPMS, logs, mantenimiento, energía, instalaciones;
- documentos administrativos: facturas, contratos, pagos, proveedores, cuentas, documentación interna;
- documentos comerciales: propuestas, ofertas, pricing, oportunidades, materiales comerciales.

El documento final debe conservar el canon Grid Code:

- header repetido en todas las páginas,
- footer repetido en todas las páginas,
- contenido fluyendo entre ambos,
- fondo oscuro corporativo,
- autor dinámico institucional,
- numeración `Página X / Y`,
- nomenclatura guardada por familia documental.

## Principio rector

No diseñar una hoja A4 interna dentro de otra hoja A4.

En Grid Code, la única página real es `@page`.
El HTML debe comportarse como documento normal y WeasyPrint se encarga de paginar.

## Motor de render

La implementación canónica usa WeasyPrint.

No usar:

- Chromium,
- Puppeteer,
- Playwright,
- JavaScript,
- header/footer fixed-position.

## Estructura canónica

El HTML debe seguir esta lógica:

```html
<body>
  <header class="header">...</header>
  <footer class="footer-fixed">...</footer>

  <div class="body-shell">
    <div class="content-frame">
      <div class="addressed-banner">...</div>
      <section class="case-title-section">...</section>
      <main class="main-flow">
        <div class="body-content">
          {{ body_content | safe if body_content else '' }}
        </div>
      </main>
    </div>
  </div>
</body>
```

Importante:

- `header` y `footer` existen una sola vez en HTML.
- WeasyPrint los convierte en running elements.
- El footer debe ir antes del contenido principal para repetirse correctamente desde la primera página.
- No duplicar footer dentro del body.
- No dejar frame de firma/validación salvo que se pida expresamente.

## CSS canónico

```css
@page {
  size: A4 portrait;
  margin-top: 34mm;
  margin-right: 0;
  margin-bottom: 22mm;
  margin-left: 0;
  background: #001518;

  @top-center {
    content: element(page-header);
    width: 100%;
  }

  @bottom-center {
    content: element(page-footer);
    width: 100%;
  }
}

.header {
  position: running(page-header);
}

.footer-fixed {
  position: running(page-footer);
}

html,
body {
  margin: 0;
  padding: 0;
  background: #001518;
  color: var(--gc-white);
}

.body-shell {
  margin: 0;
  padding: 0 12mm;
  background: transparent;
}

.page,
.body-shell,
.content-frame,
.main-flow {
  width: auto;
  min-width: 0;
  max-width: none;
  height: auto;
  min-height: auto;
  margin: 0;
  padding: 0;
  background: transparent;
  display: block;
}
```

## Reglas operativas obligatorias

1. No usar `position: fixed` para header/footer.
2. No usar `position: absolute` para header/footer.
3. No usar wrappers internos con `width: 210mm`, `height: 297mm`, `min-height: 297mm` o `margin: auto`.
4. No usar footer notes dentro del body si el footer ya se repite por página.
5. No usar una firma/validación de gran tamaño que empuje el pie de página.
6. No usar `break-inside: avoid` en wrappers grandes.
7. No usar `margin-top: auto` para empujar secciones.
8. No depender de padding manual para compensar header/footer; el espacio real lo reservan los márgenes de `@page`.

## Familias documentales

La skill trabaja con tres familias documentales.

### Técnico

Contenido con términos como:

- técnico
- diagnóstico
- anomalía
- OCPP
- DLM
- CPMS
- cargador
- energía
- log
- mantenimiento
- instalación
- corriente
- fase
- potencia

Autor institucional:

- `Departamento Técnico`

Prefijo de guardado:

- `T`

### Administrativo

Contenido con términos como:

- factura
- facturación
- pago
- contrato
- administrativo
- proveedor
- cuenta
- orden de compra
- documentación interna

Autor institucional:

- `Departamento Administrativo`

Prefijo de guardado:

- `A`

### Comercial

Contenido con términos como:

- propuesta
- oferta
- comercial
- venta
- pricing
- cliente potencial
- oportunidad
- cotización
- presupuesto

Autor institucional:

- `Departamento Comercial`

Prefijo de guardado:

- `C`

### Regla de desempate

Si hay duda, elegir Técnico.

## Resolución dinámica del autor

La skill no debe usar un autor personal fijo en producción.

Debe resolver el departamento según el contenido y escribirlo en el header como autor institucional.

### Lógica sugerida

```python
def resolve_author_department(content_text="", document_type=""):
    text = f"{document_type} {content_text}".lower()

    commercial_terms = [
        "propuesta", "oferta", "comercial", "venta", "pricing",
        "cliente potencial", "oportunidad", "cotización", "presupuesto"
    ]

    admin_terms = [
        "factura", "facturación", "pago", "contrato", "administrativo",
        "proveedor", "cuenta", "orden de compra", "documentación interna"
    ]

    technical_terms = [
        "técnico", "diagnóstico", "ocpp", "dlm", "cpms", "cargador",
        "energía", "anomalía", "log", "mantenimiento", "instalación",
        "corriente", "fase", "potencia"
    ]

    if any(term in text for term in commercial_terms):
        return "Departamento Comercial", "C"

    if any(term in text for term in admin_terms):
        return "Departamento Administrativo", "A"

    if any(term in text for term in technical_terms):
        return "Departamento Técnico", "T"

    return "Departamento Técnico", "T"
```

## Nomenclatura de guardado

El documento final debe guardarse con prefijo de familia:

- Técnico → `T`
- Administrativo → `A`
- Comercial → `C`

### Formato recomendado

`<PREFIX>-<report_code>-<normalized_title>-<YYYYMMDD>.pdf`

### Ejemplos

- `T-IAP-GC-20260609-RE01-hidrica-group-20260609.pdf`
- `A-GC-INV-20260609-0001-factura-servicios-20260609.pdf`
- `C-GC-PRP-20260609-0003-oferta-gridcode-20260609.pdf`

## Footer canónico

El footer debe ser breve, repetido por página y sin email.

Texto recomendado:

`Documento confidencial · Uso interno y destinatarios autorizados · Protección de datos UE`

Debe contener además:

- `grid-code.tech`
- `Página X / Y`

Ejemplo:

```html
<footer class="footer-fixed">
  <div class="footer-text">
    <span>GRIDCODE</span> · grid-code.tech<br>
    {{ confidentiality_text or 'Documento confidencial · Uso interno y destinatarios autorizados · Protección de datos UE' }}
  </div>
  <div class="footer-right">
    Grid Code · Transición Energética<br>
    Página <span class="page-number"></span>
  </div>
</footer>
```

## Checklist de aceptación

El PDF solo se considera correcto si cumple todo esto:

1. Header aparece en todas las páginas.
2. Footer aparece en todas las páginas.
3. Header ocupa todo el ancho.
4. Footer ocupa todo el ancho.
5. El contenido no invade el header.
6. El contenido no invade el footer.
7. No existe wrapper A4 interno.
8. No existe footer duplicado dentro del body.
9. No existe texto de firma/validación si no fue pedido.
10. No existe email en el footer.
11. La numeración es correcta (`Página X / Y`).
12. El autor es institucional y coincide con la familia documental.
13. La nomenclatura guardada lleva el prefijo correcto `T/A/C`.
14. No aparece página vacía extra.
15. El fondo oscuro cubre toda la hoja.

## Flujo operativo recomendado

1. Recibir el contenido o HTML base.
2. Clasificar la familia documental.
3. Resolver `author_department` y el prefijo `T/A/C`.
4. Renderizar con WeasyPrint bajo el canon Grid Code.
5. Guardar el PDF con nomenclatura departamental.
6. Verificar la salida final antes de entregarla.

## Estado del canon

Esta documentación define la forma oficial de producir documentos Grid Code con estilo unificado.

A partir de aquí, cualquier nuevo documento Grid Code debe seguir esta skill como fuente única de verdad.
