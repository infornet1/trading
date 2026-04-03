/**
 * VIZNIAGO FURY — i18n
 * Bilingual support: Spanish (default) / English
 *
 * Usage in HTML:
 *   data-i18n="key"       → sets el.textContent
 *   data-i18n-html="key"  → sets el.innerHTML  (for strings with tags)
 *
 * Usage in JS:
 *   window.t('key')              → translated string
 *   window.setLanguage('es'|'en')
 */

const TRANSLATIONS = {

  /* ══════════════════════════════════════════════════════════════
     ESPAÑOL
  ══════════════════════════════════════════════════════════════ */
  es: {
    // ── Landing: navbar ──────────────────────────────────────────
    'nav.title':                 'LP + Perps Hedge Backtester',
    'nav.dashboard':             '📈 Panel en Vivo',
    'nav.docs':                  'Docs',
    'nav.defi.dashboard':        'LP Defensor',
    'nav.defi.dashboard.sub':    'Bots LP en vivo',
    'nav.soon':                  'Próximamente',

    // ── Landing: hero ─────────────────────────────────────────────
    'hero.label':             'Investigación de Estrategia DeFi',
    'hero.h1.line1':          'LP + Perps Hedge',
    'hero.h1.line2':          'Motor de Backtest',
    'hero.desc':              'Simula posiciones de liquidez concentrada (estilo Uniswap v3) en BTC/USDT y cubre automáticamente la pérdida impermanente abriendo SHORTs en perps cuando el precio sale de tu rango LP.',
    'hero.btn.explore':       'Explorar Estrategias',
    'hero.btn.howto':         'Cómo Funciona',
    'hero.stat.strategies':   'Estrategias',
    'hero.stat.metrics':      'Métricas',
    'hero.stat.pair':         'Par',

    // ── Landing: strategies ───────────────────────────────────────
    'strat.label':       'Comparación Principal',
    'strat.title':       'Tres Estrategias, Una Verdad',
    'strat.desc':        'Ejecuta las tres estrategias con los mismos datos de precio y observa exactamente dónde se compensan las comisiones, la pérdida impermanente y los costos de cobertura.',
    'strat.01.num':      'ESTRATEGIA 01',
    'strat.01.name':     'HODL 50/50',
    'strat.01.desc':     'Mantén 50% BTC + 50% USDT. Sin gestión activa. Exposición pura al precio como benchmark de referencia.',
    'strat.01.pro1':     'Sin costos de gas / protocolo',
    'strat.01.pro2':     'Ganancia completa en precio de BTC',
    'strat.01.con1':     'Sin rendimiento en USDT inactivo',
    'strat.01.con2':     '50% del portfolio en stablecoin',
    'strat.02.num':      'ESTRATEGIA 02',
    'strat.02.name':     'Solo LP',
    'strat.02.desc':     'Provee liquidez concentrada en un pool BTC/USDT. Gana comisiones de trading mientras estás expuesto a pérdida impermanente cuando el precio sale de tu rango.',
    'strat.02.pro1':     'Ganar comisiones LP continuamente',
    'strat.02.pro2':     'Eficiencia de capital amplificada vs v2',
    'strat.02.con1':     'Pérdida impermanente fuera del rango',
    'strat.02.con2':     'Requiere gestión activa del rango',
    'strat.03.num':      'ESTRATEGIA 03',
    'strat.03.name':     'LP + Cobertura',
    'strat.03.desc':     'Combina los ingresos por comisiones LP con un SHORT de perpetuos que se activa cuando el precio cae por debajo de tu rango, capturando protección bajista mientras mantiene el rendimiento.',
    'strat.03.pro1':     'Comisiones LP + ganancias de SHORT perp',
    'strat.03.pro2':     'PI compensada por P&G de cobertura',
    'strat.03.pro3':     'Ratio de cobertura configurable',
    'strat.03.con1':     'Costo de tasa de financiamiento en SHORT',
    'strat.03.tag':      '★ Estrategia Principal',

    // ── Landing: bot explainer ────────────────────────────────────
    'bot.label':            'Delta Bot Defensor',
    'bot.title':            '¿Cómo Te Protege el Bot?',
    'bot.desc':             'Cuando el precio de ETH cae fuera de tu rango de liquidez, el bot abre automáticamente un SHORT en Hyperliquid para compensar la pérdida impermanente. Mira la simulación en tiempo real y experimenta con el slider para entenderlo de forma intuitiva.',
    'bot.chart.title':      'Simulación Animada en Vivo',
    'bot.chart.loop':       '↺ Loop automático',
    'bot.stat.lp':          'Valor Posición LP',
    'bot.stat.lp.note':     'En rango — acumulando comisiones',
    'bot.stat.hedge':       'P&G Cobertura SHORT',
    'bot.stat.hedge.note':  'Bot inactivo — precio en rango',
    'bot.stat.net':         'Resultado Neto',
    'bot.stat.net.note':    'LP + Cobertura combinados',
    'bot.sim.title':        'SIMULADOR INTERACTIVO',
    'bot.sim.sub':          'Arrastra el slider para ver cómo responde el bot a cada precio',
    'bot.sim.eth':          'Precio ETH',
    'bot.sim.lp':           'Posición LP',
    'bot.sim.hedge':        'Cobertura SHORT',
    'bot.sim.net':          'Resultado Neto',
    'bot.sim.note':         '* Simulación simplificada. Capital LP: $10,000 · Rango ETH: $1,800–$2,400 · Ratio cobertura: 80%',
    'bot.lifecycle.title':  'CICLO DE VIDA DEL BOT',
    'bot.lc.01.title':      'Configurar',
    'bot.lc.01.desc':       'Defines tu rango LP, ratio de cobertura, apalancamiento y stop-loss. El bot aprende los parámetros de tu estrategia.',
    'bot.lc.02.title':      'Vigilar',
    'bot.lc.02.desc':       'Precio dentro del rango. El LP acumula comisiones de trading. El bot monitorea el precio cada 30 segundos — sin acción necesaria.',
    'bot.lc.03.title':      'Disparar',
    'bot.lc.03.desc':       'Precio sale del rango. El bot abre automáticamente un SHORT en Hyperliquid. La cobertura entra en acción al instante.',
    'bot.lc.04.title':      'Recuperar',
    'bot.lc.04.desc':       'Precio vuelve al rango. El SHORT se cierra con ganancia. Auto-rearm activo: el bot se resetea y vuelve al paso 02.',

    // ── Landing: how it works ─────────────────────────────────────
    'how.label':         'Pipeline',
    'how.title':         'Cómo Funciona el Backtest',
    'how.desc':          'Cuatro pasos deterministas desde datos de precio brutos hasta un informe de rendimiento completo.',
    'how.01.title':      'Obtener Datos de Precio',
    'how.01.desc':       'Obtén velas OHLCV de Binance para el rango de fechas elegido y el intervalo (1h / 4h / 1d).',
    'how.02.title':      'Simular Posición LP',
    'how.02.desc':       'Modela la matemática de liquidez concentrada de Uniswap v3: balances de tokens, comisiones ganadas y estado dentro/fuera del rango por vela.',
    'how.03.title':      'Aplicar Lógica de Cobertura',
    'how.03.desc':       'Abre SHORT perp cuando el precio cae por debajo del tick inferior. Aplica costos de tasa de financiamiento y P&G en cada vela fuera del rango.',
    'how.04.title':      'Reportar y Comparar',
    'how.04.desc':       'Calcula Sharpe, Sortino, Drawdown Máximo, Factor de Beneficio y grafica curvas de capital lado a lado para las tres estrategias.',

    // ── Landing: metrics ──────────────────────────────────────────
    'metrics.label':     'Análisis de Rendimiento',
    'metrics.title':     'Suite Completa de Métricas',
    'metrics.desc':      'Cada ejecución de estrategia produce un desglose completo del rendimiento ajustado al riesgo.',
    'metrics.01.name':   'Retorno Total',
    'metrics.01.desc':   'Ganancia neta del portfolio relativa al capital inicial durante toda la ventana de backtest.',
    'metrics.02.name':   'Retorno Anualizado',
    'metrics.02.desc':   'Normalizado a 365 días. Compara estrategias independientemente de la duración del backtest.',
    'metrics.03.name':   'Ratio Sharpe',
    'metrics.03.desc':   'Retorno ajustado al riesgo anualizado usando períodos horarios. >1.0 = bueno, >2.0 = excelente.',
    'metrics.04.name':   'Ratio Sortino',
    'metrics.04.desc':   'Como Sharpe pero solo penaliza la desviación bajista — mejor para estrategias asimétricas.',
    'metrics.05.name':   'Drawdown Máximo',
    'metrics.05.desc':   'Mayor caída de capital de pico a valle. Medida clave del riesgo de capital en el peor momento.',
    'metrics.06.name':   'Factor de Beneficio',
    'metrics.06.desc':   'Ganancias totales divididas por pérdidas totales por vela. Valores >1.5 indican una ventaja sólida.',

    // ── Landing: integrations ─────────────────────────────────────
    'int.label':         'Datos y Protocolos',
    'int.title':         'Construido en Infraestructura Probada',
    'int.desc':          'El backtester modela los mismos mecanismos que encuentras en DeFi en producción.',
    'int.01.name':       'Binance OHLCV',
    'int.01.desc':       'Klines históricas de BTC/USDT via API REST pública. Intervalos 1h, 4h, 1d.',
    'int.02.name':       'Matemática Uniswap v3',
    'int.02.desc':       'Modelo completo de liquidez concentrada con seguimiento basado en ticks y simulación de comisiones.',
    'int.03.name':       'Financiamiento Perps',
    'int.03.desc':       'Modelo de tasa de financiamiento configurable. Soporta APY fijo o tasa por período de 8h.',
    'int.04.name':       'Modelo de Costos',
    'int.04.desc':       'Slippage, comisiones de protocolo y costos de gas incluidos en cada evento de entrada y salida.',

    // ── Landing: CTA ──────────────────────────────────────────────
    'cta.label':              'Listo para Participar',
    'cta.title':              'Únete a la Lista de Espera',
    'cta.desc':               'Regálanos tu correo electrónico y te avisaremos en cuanto abran los primeros accesos.',
    'cta.email.placeholder':  'tu@correo.com',
    'cta.btn':                'Notifícame',

    // ── Landing: footer ───────────────────────────────────────────
    'footer.text':       'DeFi LP Platform — VIZNIAGO © 2026',
    'footer.strategies': 'Estrategias',
    'footer.metrics':    'Métricas',
    'footer.docs':       'Docs',
    'footer.telegram':   'Alertas en Telegram — @vizniago_bot',

    // ── Dashboard: navbar ─────────────────────────────────────────
    'dash.nav.title':          'Panel de Control LP',

    // ── Dashboard: price ticker ───────────────────────────────────
    'dash.ticker.eth':         'ETH/USDC',
    'dash.ticker.btc':         'BTC/USDT',
    'dash.ticker.fetching':    'Obteniendo precios…',

    // ── Dashboard: connect prompt ─────────────────────────────────
    'dash.connect.title':      'Conectar tu Billetera',
    'dash.connect.desc':       'Conecta Rabby o cualquier billetera EIP-1193 para ver tus posiciones LP de Uniswap\u00A0v3 en vivo en Arbitrum, Base o Ethereum.',
    'dash.connect.btn':        '🟢\u00A0 Conectar Billetera',
    'dash.connect.hint':       'Compatible con: Rabby Wallet · MetaMask · cualquier billetera EIP-1193',
    'dash.connect.nowallet':   'No se detectó billetera.',
    'dash.connect.download':   'Descargar Rabby ↗',

    // ── Dashboard: wallet bar ─────────────────────────────────────
    'dash.ws.refresh':         '↻\u00A0 Actualizar',
    'dash.ws.disconnect':      'Desconectar',

    // ── Dashboard: network warning ────────────────────────────────
    'dash.wrongnet':           '⚠\u00A0 Cambia a <strong>Arbitrum One</strong>, Ethereum o Base para ver posiciones Uniswap\u00A0v3. Red actual:',

    // ── Dashboard: tabs ───────────────────────────────────────────
    'dash.tab.active':              'Activas',
    'dash.tab.history':             'Historial',

    // ── Dashboard: states ─────────────────────────────────────────
    'dash.loading.text':            'Obteniendo posiciones on-chain…',
    'dash.nopos.title':             'Sin Posiciones Activas',
    'dash.nopos.desc':              'No se encontraron NFTs LP activos para esta billetera en la red actual. Crea una posición en Uniswap v3 para comenzar a monitorear.',
    'dash.nopos.history.title':     'Sin Historial de Posiciones',
    'dash.nopos.history.desc':      'Las posiciones cerradas (liquidez cero) aparecerán aquí.',

    // ── Dashboard: hedge panel ────────────────────────────────────
    'dash.hedge.label':        'Bot en Vivo',
    'dash.hedge.nft.label':    'Monitoreando NFT',
    'dash.hedge.range.label':  'Rango LP',
    'dash.hedge.range.sub':    '~25.0% de ancho',
    'dash.hedge.range.width':  'de ancho',
    'dash.hedge.trig.below':   'bajo el piso',
    'dash.hedge.trig.label':   'Disparador de Cobertura',
    'dash.hedge.trig.sub':     '−0.5% bajo el piso → SHORT 10× en HL',
    'dash.hedge.mode.label':   'Modo',
    'dash.hedge.mode.val':     'Defensor Bajista (Solo Cobertura)',
    'dash.hedge.mode.sub':     'SL +0.5% · TP en piso del rango',
    'dash.hedge.rule':         '<strong>Regla de Oro:</strong>\u00A0 BTC → NUNCA short. ETH → long+short OK. Billetera de cobertura: 10–20% del valor del pool.',

    // ── Dashboard: position cards (JS dynamic) ────────────────────
    'pos.status.inrange':      'EN RANGO',
    'pos.status.outlow':       'FUERA ↓ ABAJO',
    'pos.status.outhigh':      'FUERA ↑ ARRIBA',
    'pos.status.closed':       'CERRADA',
    'pos.range.label':         'Rango de Precio',
    'pos.price.lower':         'Límite Inferior',
    'pos.price.current':       'Precio Actual',
    'pos.price.upper':         'Límite Superior',
    'pos.fees.label':          'Comisiones Pendientes',
    'pos.fee.tier':            'Nivel de comisión:',
    'pos.range.through':       'en el rango',
    'pos.range.outlow':        'Precio <strong>por debajo</strong> del límite inferior — zona de cobertura activa',
    'pos.range.outhigh':       'Precio <strong>por encima</strong> del límite superior — todo en stablecoin',
    'pos.range.closed':        'Posición cerrada (liquidez cero)',
    'dash.count.one':          'posición',
    'dash.count.many':         'posiciones',
    'dash.btn.connect':        '🟢 Conectar Billetera',
    'dash.btn.connecting':     '⏳ Conectando…',
    'dash.rabby.detected':     'Rabby Wallet detectado ✓',

    // ── Dashboard: watch address mode ─────────────────────────
    'dash.watch.or':           'o ver una dirección',
    'dash.watch.placeholder':  '… dirección de billetera',
    'dash.watch.btn':          'Ver',
    'dash.watch.hint':         'Solo lectura — sin conexión de billetera',
    'dash.watch.badge':        '👁 VIENDO',
    'dash.watch.stop':         'Dejar de Ver',
    'dash.watch.invalid':      'Dirección inválida. Debe empezar con 0x y tener 42 caracteres.',
    'dash.watch.network':      'Red:',

    'dash.footer.text':        'Panel de Control LP — VIZNIAGO FURY © 2026',
    'dash.footer.backtest':    'Backtester',

    // ── Dashboard: protection drawer ──────────────────────────────
    'prot.drawer.title':          'Activar Protección',
    'prot.drawer.signin.hint':    'Firma un mensaje con tu billetera para activar la protección del bot.',
    'prot.mode.label':            'Modo',
    'prot.mode.aragan':           'Defensor Bajista',
    'prot.mode.aragan.desc':      'SHORT solo en caídas. En subidas, la LP captura toda la ganancia libremente.',
    'prot.mode.avaro':            'Defensor Alcista',
    'prot.mode.avaro.desc':       'SHORT en caídas + LONG en rupturas al alza. Más activo, mayor exposición.',
    'prot.mode.neutral.note':     '⚠ Ningún modo es delta-neutral continuo — ambos usan coberturas de entrada única.',
    'prot.trigger.label':         'Disparador (% bajo piso)',
    'prot.hedgesize.label':       'Tamaño Cobertura (% capital)',
    'prot.exchange.label':        'Exchange',
    'prot.apikey.label':          'Clave Privada API Wallet HL (no tu dirección)',
    'prot.apikey.placeholder':    '0x… (64 hex chars — clave privada del API Wallet)',
    'prot.apikey.keepcurrent':    'Dejar vacío para mantener actual',
    'prot.wallet.label':          'Dirección Billetera HL',
    'prot.wallet.placeholder':    '0x…',
    'prot.wallet.new':            'Ingresar nueva dirección',
    'prot.btn.activate':          'Activar Protección',
    'prot.btn.activating':        'Activando…',
    'prot.btn.stop':              'Detener Bot',
    'prot.btn.stopping':          'Deteniendo…',
    'prot.btn.signin':            'Iniciar Sesión con Billetera',
    'dash.refresh.label':         'Auto',
    'dash.admin.stop':            'Stop All',
    'dash.admin.modal.title':     'Parada de Emergencia',
    'dash.admin.modal.desc':      'Esto detendrá TODOS los bots activos para TODOS los usuarios y los marcará inactivos. Esta acción no puede deshacerse automáticamente.',
    'dash.admin.modal.confirm':   '☢ Confirmar Parada Total',
    'dash.admin.modal.cancel':    'Cancelar',
    // Whale Tracker
    'whale.leaderboard.label':    'Leaderboard',
    'whale.notional.label':       'Notional Mín.',
    'whale.notional.sub':         'Por señal',
    'whale.assets.label':         'Activos',
    'whale.mode.label':           'Modo',
    'whale.last.signal':          'Última señal',
    'whale.no.signals':           'Sin señales aún — esperando ballenas…',
    // ---
    'prot.status.active':         '🟢 ACTIVO',
    'prot.status.inactive':       '⭕ INACTIVO',
    'prot.status.checking':       'Verificando…',
    'prot.lastevent':             'Último evento',
    'prot.price':                 'Precio',
    'prot.watch.disabled':        'Protección no disponible en modo observación.',
    'prot.btc.warning':           'Pares BTC: solo modo Defensor Bajista (regla de oro: BTC nunca short).',
    'prot.btc.soon.title':        'Protección BTC — Próximamente',
    'prot.btc.soon.msg':          'Tu pool WBTC se visualiza correctamente. La activación del bot de cobertura para pares BTC está en desarrollo.',
    'prot.no.hlkey':              'Ingresa tu API Key y dirección de billetera HL.',
    'prot.signin.required':       'Inicia sesión para activar la protección del bot.',
    'prot.session.expired.msg':   'Tu sesión expiró pero el bot sigue corriendo en el servidor. Vuelve a conectarte para ver el estado en vivo y gestionar la protección.',
    'prot.btn.reauth':            'Reconectar Sesión',
    'dash.session.expired.banner':'Tu sesión expiró — tus bots siguen corriendo. Re-conéctate en cualquier pool para continuar.',
  },

  /* ══════════════════════════════════════════════════════════════
     ENGLISH
  ══════════════════════════════════════════════════════════════ */
  en: {
    // ── Landing: navbar ──────────────────────────────────────────
    'nav.title':                 'LP + Perps Hedge Backtester',
    'nav.dashboard':             '📈 Live Dashboard',
    'nav.docs':                  'Docs',
    'nav.defi.dashboard':        'LP Defensor',
    'nav.defi.dashboard.sub':    'Live LP hedge bots',
    'nav.soon':                  'Coming soon',

    // ── Landing: hero ─────────────────────────────────────────────
    'hero.label':             'DeFi Strategy Research',
    'hero.h1.line1':          'LP + Perps Hedge',
    'hero.h1.line2':          'Backtest Engine',
    'hero.desc':              'Simulate concentrated liquidity positions (Uniswap v3 style) on BTC/USDT and automatically hedge impermanent loss by opening SHORT perps when price exits your LP range.',
    'hero.btn.explore':       'Explore Strategies',
    'hero.btn.howto':         'How It Works',
    'hero.stat.strategies':   'Strategies',
    'hero.stat.metrics':      'Metrics',
    'hero.stat.pair':         'Pair',

    // ── Landing: strategies ───────────────────────────────────────
    'strat.label':       'Core Comparison',
    'strat.title':       'Three Strategies, One Truth',
    'strat.desc':        'Run all three approaches on the same price data and see exactly where fees, impermanent loss, and hedging costs net out.',
    'strat.01.num':      'STRATEGY 01',
    'strat.01.name':     'HODL 50/50',
    'strat.01.desc':     'Hold 50% BTC + 50% USDT. No active management. Pure price exposure as the baseline benchmark.',
    'strat.01.pro1':     'Zero gas / protocol costs',
    'strat.01.pro2':     'Full upside on BTC price',
    'strat.01.con1':     'No yield on idle USDT',
    'strat.01.con2':     '50% portfolio in stablecoin',
    'strat.02.num':      'STRATEGY 02',
    'strat.02.name':     'LP Only',
    'strat.02.desc':     'Provide concentrated liquidity in a BTC/USDT pool. Earn trading fees while being exposed to impermanent loss when price moves outside your range.',
    'strat.02.pro1':     'Earn LP fees continuously',
    'strat.02.pro2':     'Amplified capital efficiency vs v2',
    'strat.02.con1':     'Impermanent loss when out-of-range',
    'strat.02.con2':     'Active range management required',
    'strat.03.num':      'STRATEGY 03',
    'strat.03.name':     'LP + Hedge',
    'strat.03.desc':     'Combine LP fee income with a perpetuals SHORT that activates when price drops below your range — capturing downside protection while keeping fee yield.',
    'strat.03.pro1':     'LP fees + SHORT perp gains',
    'strat.03.pro2':     'IL offset by hedge P&L',
    'strat.03.pro3':     'Configurable hedge ratio',
    'strat.03.con1':     'Funding rate cost on SHORT',
    'strat.03.tag':      '★ Focus Strategy',

    // ── Landing: bot explainer ────────────────────────────────────
    'bot.label':            'Delta Bot Defensor',
    'bot.title':            'How Does the Bot Protect You?',
    'bot.desc':             'When the ETH price drops outside your liquidity range, the bot automatically opens a SHORT on Hyperliquid to offset impermanent loss. Watch the live simulation and drag the slider to understand it intuitively.',
    'bot.chart.title':      'Live Animated Simulation',
    'bot.chart.loop':       '↺ Auto loop',
    'bot.stat.lp':          'LP Position Value',
    'bot.stat.lp.note':     'In range — accumulating fees',
    'bot.stat.hedge':       'Hedge P&L (SHORT)',
    'bot.stat.hedge.note':  'Bot idle — price in range',
    'bot.stat.net':         'Net Result',
    'bot.stat.net.note':    'LP + Hedge combined',
    'bot.sim.title':        'INTERACTIVE SIMULATOR',
    'bot.sim.sub':          'Drag the slider to see how the bot responds to each price',
    'bot.sim.eth':          'ETH Price',
    'bot.sim.lp':           'LP Position',
    'bot.sim.hedge':        'SHORT Hedge',
    'bot.sim.net':          'Net Result',
    'bot.sim.note':         '* Simplified simulation. LP Capital: $10,000 · ETH Range: $1,800–$2,400 · Hedge ratio: 80%',
    'bot.lifecycle.title':  'BOT LIFECYCLE',
    'bot.lc.01.title':      'Configure',
    'bot.lc.01.desc':       'Set your LP range, hedge ratio, leverage, and stop-loss. The bot learns your strategy parameters.',
    'bot.lc.02.title':      'Watch',
    'bot.lc.02.desc':       'Price inside range. LP accumulates trading fees. Bot monitors price every 30 seconds — no action needed.',
    'bot.lc.03.title':      'Trigger',
    'bot.lc.03.desc':       'Price exits range. Bot automatically opens a SHORT on Hyperliquid. Hedge activates instantly.',
    'bot.lc.04.title':      'Recover',
    'bot.lc.04.desc':       'Price returns to range. SHORT closes with profit. Auto-rearm: bot resets and returns to step 02.',

    // ── Landing: how it works ─────────────────────────────────────
    'how.label':         'Pipeline',
    'how.title':         'How The Backtest Works',
    'how.desc':          'Four deterministic steps from raw price data to a full performance report.',
    'how.01.title':      'Fetch Price Data',
    'how.01.desc':       'Pull OHLCV candles from Binance for your chosen date range and interval (1h / 4h / 1d).',
    'how.02.title':      'Simulate LP Position',
    'how.02.desc':       'Model Uniswap v3 concentrated liquidity math — token balances, fees earned, and in/out-of-range status per candle.',
    'how.03.title':      'Apply Hedge Logic',
    'how.03.desc':       'Open SHORT perp when price falls below lower tick. Apply funding rate costs and PnL on each candle while out-of-range.',
    'how.04.title':      'Report & Compare',
    'how.04.desc':       'Calculate Sharpe, Sortino, Max Drawdown, Profit Factor and plot equity curves side-by-side across all three strategies.',

    // ── Landing: metrics ──────────────────────────────────────────
    'metrics.label':     'Performance Analytics',
    'metrics.title':     'Full Metrics Suite',
    'metrics.desc':      'Every strategy run produces a complete risk-adjusted performance breakdown.',
    'metrics.01.name':   'Total Return',
    'metrics.01.desc':   'Net portfolio gain relative to initial capital over the full backtest window.',
    'metrics.02.name':   'Annualized Return',
    'metrics.02.desc':   'Normalized to 365 days. Compare strategies regardless of backtest duration.',
    'metrics.03.name':   'Sharpe Ratio',
    'metrics.03.desc':   'Annualized risk-adjusted return using hourly periods. >1.0 = good, >2.0 = excellent.',
    'metrics.04.name':   'Sortino Ratio',
    'metrics.04.desc':   'Like Sharpe but only penalises downside deviation — better for asymmetric strategies.',
    'metrics.05.name':   'Max Drawdown',
    'metrics.05.desc':   'Largest peak-to-trough equity drop. Key measure of capital risk at the worst moment.',
    'metrics.06.name':   'Profit Factor',
    'metrics.06.desc':   'Total gains divided by total losses per candle. Values >1.5 indicate a strong edge.',

    // ── Landing: integrations ─────────────────────────────────────
    'int.label':         'Data & Protocols',
    'int.title':         'Built On Proven Infrastructure',
    'int.desc':          'The backtester models the same mechanics you encounter in production DeFi.',
    'int.01.name':       'Binance OHLCV',
    'int.01.desc':       'Historical BTC/USDT klines via public REST API. 1h, 4h, 1d intervals.',
    'int.02.name':       'Uniswap v3 Math',
    'int.02.desc':       'Full concentrated liquidity model with tick-based position tracking and fee simulation.',
    'int.03.name':       'Perps Funding',
    'int.03.desc':       'Configurable funding rate model. Supports fixed APY or per-8h rate assumptions.',
    'int.04.name':       'Cost Model',
    'int.04.desc':       'Slippage, protocol fees, and gas costs factored in at every entry and exit event.',

    // ── Landing: CTA ──────────────────────────────────────────────
    'cta.label':              'Ready to Join',
    'cta.title':              'Join the Waiting List',
    'cta.desc':               'Drop us your email and we\'ll notify you as soon as early access opens.',
    'cta.email.placeholder':  'your@email.com',
    'cta.btn':                'Notify Me',

    // ── Landing: footer ───────────────────────────────────────────
    'footer.text':       'DeFi LP Platform — VIZNIAGO © 2026',
    'footer.strategies': 'Strategies',
    'footer.metrics':    'Metrics',
    'footer.docs':       'Docs',
    'footer.telegram':   'Real-time Alerts — @vizniago_bot',

    // ── Dashboard: navbar ─────────────────────────────────────────
    'dash.nav.title':          'LP Pool Dashboard',

    // ── Dashboard: price ticker ───────────────────────────────────
    'dash.ticker.eth':         'ETH/USDC',
    'dash.ticker.btc':         'BTC/USDT',
    'dash.ticker.fetching':    'Fetching prices…',

    // ── Dashboard: connect prompt ─────────────────────────────────
    'dash.connect.title':      'Connect Your Wallet',
    'dash.connect.desc':       'Connect Rabby or any EIP-1193 wallet to view your live Uniswap\u00A0v3 LP positions on Arbitrum, Base, or Ethereum.',
    'dash.connect.btn':        '🟢\u00A0 Connect Wallet',
    'dash.connect.hint':       'Supports: Rabby Wallet · MetaMask · any EIP-1193 wallet',
    'dash.connect.nowallet':   'No wallet detected.',
    'dash.connect.download':   'Download Rabby ↗',

    // ── Dashboard: wallet bar ─────────────────────────────────────
    'dash.ws.refresh':         '↻\u00A0 Refresh',
    'dash.ws.disconnect':      'Disconnect',

    // ── Dashboard: network warning ────────────────────────────────
    'dash.wrongnet':           '⚠\u00A0 Switch to <strong>Arbitrum One</strong>, Ethereum, or Base to see Uniswap\u00A0v3 positions. Current chain:',

    // ── Dashboard: tabs ───────────────────────────────────────────
    'dash.tab.active':              'Active',
    'dash.tab.history':             'History',

    // ── Dashboard: states ─────────────────────────────────────────
    'dash.loading.text':            'Fetching on-chain positions…',
    'dash.nopos.title':             'No Active Positions',
    'dash.nopos.desc':              'No active LP NFTs found for this wallet on the current network. Create a position on Uniswap v3 to start monitoring.',
    'dash.nopos.history.title':     'No Position History',
    'dash.nopos.history.desc':      'Closed positions (zero liquidity) will appear here.',

    // ── Dashboard: hedge panel ────────────────────────────────────
    'dash.hedge.label':        'Live Bot',
    'dash.hedge.nft.label':    'Monitoring NFT',
    'dash.hedge.range.label':  'LP Range',
    'dash.hedge.range.sub':    '~25.0% width',
    'dash.hedge.range.width':  'width',
    'dash.hedge.trig.below':   'below floor',
    'dash.hedge.trig.label':   'Hedge Trigger',
    'dash.hedge.trig.sub':     '−0.5% below floor → 10× SHORT on HL',
    'dash.hedge.mode.label':   'Mode',
    'dash.hedge.mode.val':     'Defensor Bajista (Hedge Only)',
    'dash.hedge.mode.sub':     'SL +0.5% · TP at range floor',
    'dash.hedge.rule':         '<strong>Golden Rule:</strong>\u00A0 BTC → NEVER short. ETH → long+short OK. Hedge wallet: 10–20% of pool value.',

    // ── Dashboard: position cards (JS dynamic) ────────────────────
    'pos.status.inrange':      'IN RANGE',
    'pos.status.outlow':       'OUT ↓ BELOW',
    'pos.status.outhigh':      'OUT ↑ ABOVE',
    'pos.status.closed':       'CLOSED',
    'pos.range.label':         'Price Range',
    'pos.price.lower':         'Lower Bound',
    'pos.price.current':       'Current Price',
    'pos.price.upper':         'Upper Bound',
    'pos.fees.label':          'Fees Owed',
    'pos.fee.tier':            'Fee tier:',
    'pos.range.through':       'through range',
    'pos.range.outlow':        'Price is <strong>below</strong> lower bound — hedge active zone',
    'pos.range.outhigh':       'Price is <strong>above</strong> upper bound — all in stablecoin',
    'pos.range.closed':        'Position closed (zero liquidity)',
    'dash.count.one':          'position',
    'dash.count.many':         'positions',
    'dash.btn.connect':        '🟢 Connect Wallet',
    'dash.btn.connecting':     '⏳ Connecting…',
    'dash.rabby.detected':     'Rabby Wallet detected ✓',

    // ── Dashboard: watch address mode ─────────────────────────
    'dash.watch.or':           'or watch an address',
    'dash.watch.placeholder':  '… wallet address',
    'dash.watch.btn':          'Watch',
    'dash.watch.hint':         'Read-only — no wallet connection required',
    'dash.watch.badge':        '👁 WATCHING',
    'dash.watch.stop':         'Stop Watching',
    'dash.watch.invalid':      'Invalid address. Must start with 0x and be 42 characters.',
    'dash.watch.network':      'Network:',

    'dash.footer.text':        'LP Pool Dashboard — VIZNIAGO FURY © 2026',
    'dash.footer.backtest':    'Backtester',

    // ── Dashboard: protection drawer ──────────────────────────────
    'prot.drawer.title':          'Enable Protection',
    'prot.drawer.signin.hint':    'Sign a message with your wallet to enable bot protection.',
    'prot.mode.label':            'Mode',
    'prot.mode.aragan':           'Defensor Bajista',
    'prot.mode.aragan.desc':      'SHORT on downside only. On upside, LP captures all gains freely.',
    'prot.mode.avaro':            'Defensor Alcista',
    'prot.mode.avaro.desc':       'SHORT on downside + LONG on upside breakouts. More active, higher exposure.',
    'prot.mode.neutral.note':     '⚠ Neither mode is continuous delta-neutral — both use single-entry hedges.',
    'prot.trigger.label':         'Trigger (% below floor)',
    'prot.hedgesize.label':       'Hedge Size (% of capital)',
    'prot.exchange.label':        'Exchange',
    'prot.apikey.label':          'HL API Wallet Private Key (not your address)',
    'prot.apikey.placeholder':    '0x… (64 hex chars — API Wallet private key)',
    'prot.apikey.keepcurrent':    'Leave blank to keep current',
    'prot.wallet.label':          'HL Wallet Address',
    'prot.wallet.placeholder':    '0x…',
    'prot.wallet.new':            'Enter new address',
    'prot.btn.activate':          'Activate Protection',
    'prot.btn.activating':        'Activating…',
    'prot.btn.stop':              'Stop Bot',
    'prot.btn.stopping':          'Stopping…',
    'prot.btn.signin':            'Sign In with Wallet',
    'dash.refresh.label':         'Auto',
    'dash.admin.stop':            'Stop All',
    'dash.admin.modal.title':     'Emergency Stop',
    'dash.admin.modal.desc':      'This will terminate ALL active bots for ALL users and mark them inactive. This action cannot be automatically undone.',
    'dash.admin.modal.confirm':   '☢ Confirm Full Stop',
    'dash.admin.modal.cancel':    'Cancel',
    // Whale Tracker
    'whale.leaderboard.label':    'Leaderboard',
    'whale.notional.label':       'Min. Notional',
    'whale.notional.sub':         'Per signal',
    'whale.assets.label':         'Assets',
    'whale.mode.label':           'Mode',
    'whale.last.signal':          'Last signal',
    'whale.no.signals':           'No signals yet — waiting for whales…',
    // ---
    'prot.status.active':         '🟢 ACTIVE',
    'prot.status.inactive':       '⭕ INACTIVE',
    'prot.status.checking':       'Checking…',
    'prot.lastevent':             'Last event',
    'prot.price':                 'Price',
    'prot.watch.disabled':        'Protection not available in watch mode.',
    'prot.btc.warning':           'BTC pairs: Defensor Bajista only (golden rule: never short BTC).',
    'prot.btc.soon.title':        'BTC Protection — Coming Soon',
    'prot.btc.soon.msg':          'Your WBTC pool is displayed correctly. Bot hedge activation for BTC pairs is currently in development.',
    'prot.no.hlkey':              'Enter your HL API Key and wallet address.',
    'prot.signin.required':       'Sign in to enable bot protection.',
    'prot.session.expired.msg':   'Your session expired but the bot is still running on the server. Re-sign to view live status and manage your protection.',
    'prot.btn.reauth':            'Reconnect Session',
    'dash.session.expired.banner':'Your session expired — your bots are still running. Re-connect on any pool to continue.',
  },
};

// ── Core functions ────────────────────────────────────────────────────────

window.currentLang = localStorage.getItem('vf_lang') || 'es';

window.t = function (key) {
  return TRANSLATIONS[window.currentLang]?.[key]
      ?? TRANSLATIONS['en']?.[key]
      ?? key;
};

window.setLanguage = function (lang) {
  if (!TRANSLATIONS[lang]) return;
  window.currentLang = lang;
  localStorage.setItem('vf_lang', lang);
  applyTranslations();
};

function applyTranslations() {
  const lang = window.currentLang;

  // Plain text nodes
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const val = window.t(el.dataset.i18n);
    if (val) el.textContent = val;
  });

  // Placeholder attributes (inputs)
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const val = window.t(el.dataset.i18nPlaceholder);
    if (val) el.placeholder = val;
  });

  // HTML content (strings that contain tags like <strong>)
  document.querySelectorAll('[data-i18n-html]').forEach(el => {
    const val = window.t(el.dataset.i18nHtml);
    if (val) el.innerHTML = val;
  });

  // <html lang="…">
  document.documentElement.lang = lang;

  // <title>
  const titleKey = document.documentElement.dataset.i18nTitle;
  if (titleKey) document.title = window.t(titleKey);

  // Language toggle buttons
  document.querySelectorAll('[data-lang-btn]').forEach(btn => {
    btn.classList.toggle('lang-btn--active', btn.dataset.langBtn === lang);
  });
}

// Apply on DOM ready
document.addEventListener('DOMContentLoaded', applyTranslations);
