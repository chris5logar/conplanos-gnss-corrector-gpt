# CONPLANOS GNSS V10.4 — Manual de efemérides

## Qué se corrigió

La V10.4 cambia el buscador de efemérides para no depender de un único servidor.

Orden estricto por cada fecha:

1. **Final**
2. Si no existe/verifica: **Rapid**
3. Si no existe/verifica: **Ultra-Rapid**
4. Si ningún producto real responde: se informa que no fue verificado.

## Fuentes consultadas

### Final
- ESA Navigation Office
- GFZ Data Center
- IGS/CDDIS como respaldo

### Rapid
- ESA Navigation Office
- GFZ Data Center
- IGS/CDDIS como respaldo

### Ultra-Rapid
- ESA Navigation Office
- GFZ Data Center
- IGS/CDDIS como respaldo

## Corrección importante de nombres

Los productos ESA Rapid y ESA Ultra-Rapid de órbitas se buscan con el muestreo publicado de **05M**. El IGS combinado se busca con **15M**.

Ejemplos:

`ESA0OPSRAP_YYYYDDD0000_01D_05M_ORB.SP3.gz`

`ESA0OPSULT_YYYYDDDHH00_02D_05M_ORB.SP3.gz`

`IGS0OPSRAP_YYYYDDD0000_01D_15M_ORB.SP3.gz`

`IGS0OPSULT_YYYYDDDHH00_02D_15M_ORB.SP3.gz`

GFZ utiliza sus archivos públicos de Rapid/Ultra-Rapid de 05 minutos.

## Por qué ahora debe ser más rápido

La versión anterior hacía muchas comprobaciones una detrás de otra. V10.4 verifica en paralelo:

- las tres fechas (día anterior, día de lectura y día siguiente);
- las fuentes de cada nivel de prioridad;
- las distintas emisiones Ultra-Rapid.

El objetivo es que un servidor lento no bloquee toda la búsqueda.

## Verificación real

La aplicación no considera suficiente un HTTP 200. Comprueba que la respuesta tenga contenido gzip real. Una página HTML, error o respuesta de autenticación no se considera un producto disponible.

## Qué hacer en GitHub

1. Descargar `CONPLANOS_GNSS_V10_4.zip`.
2. Descomprimir.
3. Reemplazar los archivos de tu repositorio manteniendo sus nombres.
4. Hacer commit.
5. Esperar el redeploy de Streamlit Cloud.
6. Entrar a **Efemérides precisas**.
7. Probar, por ejemplo, `20/09/2026` y `22/09/2026`.

## Fuentes oficiales

IGS Products: https://www.igs.org/products/

ESA GNSS Products: https://navigation-office.esa.int/GNSS_based_products.html

GFZ GNSS Products: https://isdc-data.gfz.de/gnss/products/

## Nota

Final tiene una latencia mayor. Rapid se publica diariamente con una latencia aproximada de horas; Ultra-Rapid tiene una parte observada y otra predicha. La aplicación no debe presentar una URL como disponible sin verificar el archivo.
