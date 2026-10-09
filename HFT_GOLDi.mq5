//+------------------------------------------------------------------+
//|                                                   HFT_GOLDi.mq5  |
//|  M5 pullback scalper for GOLDi with hard blow-up protections.     |
//|  Strategy: RSI(7) pullback through 30/70 in EMA50(M5) trend.     |
//|  Validated train+test on 16.5 months of GOLDi M5 data.           |
//+------------------------------------------------------------------+
#property copyright "HFT Gold Scalper"
#property version   "1.10"
#property description "M5 RSI-pullback in trend with daily-loss, drawdown and 10x-target locks"
#include <Trade\Trade.mqh>

input group "=== Strategy (validated on M5) ==="
input string          InpSymbol   = "GOLDi";  // if missing, auto-falls back to XAUUSD/GOLD
string   gSymbol = "";
input ENUM_TIMEFRAMES InpTf       = PERIOD_M5;
input int             InpRsiPeriod = 7;
input double          InpRsiLo    = 30.0;
input double          InpRsiHi    = 70.0;
input int             InpTrendEma = 50;
input int             InpAtrPeriod = 14;
input double InpSL_Atr   = 2.0;
input double InpTP_Atr   = 2.25;

input group "=== Risk & blow-up protection ==="
input double InpRiskPercent         = 10.0;
input double InpMaxEffectiveRiskPct = 30.0;
input double InpShrinkMinAtr        = 2.0;
input int    InpMaxPositions        = 1;
input double InpMaxDailyLossPct     = 20.0;
input double InpMaxDrawdownPct      = 55.0;
input double InpTargetMultiple      = 10.0;
input int    InpMaxSpreadPts        = 45;

input group "=== Session (server time) ==="
input int InpStartHour = 7;
input int InpEndHour   = 20;

input group "=== Trade management ==="
input bool   InpTrailing          = true;
input double InpBeAtr             = 0.5;
input double InpTrailAtr          = 1.5;
input double InpTrailBufferPts    = 200;   // trailing buffer in symbol points (0 = ATR chandelier)
input int    InpHighSpreadPts     = 30;    // spread (pts) above which the wider buffer is used
input int    InpTrailBufferHiPts  = 300;   // trailing buffer (pts) when spread is high
input bool   InpUseLimitEntry     = true;  // enter via limit at signal close (fill-or-miss)
input bool   InpEveryCandle       = true;  // one 0.01 trade per candle, direction = EMA50 trend
input double InpEveryCandleLot    = 0.01;
input bool   InpConfluence        = true;  // require RSI agreement before every-candle entry
input double InpRsiUpFilter       = 70.0;  // long entry only when RSI7 below this (not overbought)
input double InpRsiDnFilter       = 30.0;  // short entry only when RSI7 above this (not oversold)
input bool   InpSlopeFilter       = true;  // long only when EMA50 rising, short only when falling
input bool   InpZoneFilter        = true;  // enter only near EMA50 (pullback zone, not extended)
input double InpZoneAtr           = 0.4;   // max |close-EMA50| in ATR units for an entry
input int    InpMagic             = 234001;
input int    InpSlippage          = 30;
input bool   InpResetProtection   = false;

input group "=== Martingale (add-on) ==="
input bool   InpMartingale   = true;    // add a leg when price moves $InpMartStepUsd against the last leg
input double InpMartStepUsd  = 1.5;
input double InpMartLot      = 0.01;
input double InpLastLegLot   = 0.02;   // lot size of the final (max-leg) trade
input int    InpMaxMartPos   = 3;

CTrade trade;
int    hRsi = INVALID_HANDLE, hTrend = INVALID_HANDLE, hAtr = INVALID_HANDLE;
datetime lastBar = 0;
string   gvBase = "", gvHalt = "";
double   gBase = 0, dayStartEquity = 0;
string   dayStamp = "";
bool     dayHalted = false, permHalted = false;
int      gDigits = 2;
double   gPoint = 0.01;
string   gStatus = "";

int OnInit()
{
   if(InpRsiLo >= InpRsiHi || InpRsiPeriod < 2 || InpTrendEma < 2)
      return(INIT_PARAMETERS_INCORRECT);
   if(InpSL_Atr <= 0 || InpTP_Atr <= 0 || InpTargetMultiple <= 1)
      return(INIT_PARAMETERS_INCORRECT);
   if(InpShrinkMinAtr > InpSL_Atr)
      return(INIT_PARAMETERS_INCORRECT);

   gSymbol = InpSymbol;
   if(!SymbolSelect(gSymbol, true))
   {
      string alts[] = {"XAUUSD", "GOLD", "GOLDi"};
      bool found = false;
      for(int i = 0; i < ArraySize(alts); i++)
         if(SymbolSelect(alts[i], true)) { gSymbol = alts[i]; found = true; break; }
      if(!found) { Print("Unknown symbol ", InpSymbol); return(INIT_PARAMETERS_INCORRECT); }
      Print("Symbol fallback: ", InpSymbol, " -> ", gSymbol);
   }

   gDigits = (int)SymbolInfoInteger(gSymbol, SYMBOL_DIGITS);
   gPoint  = SymbolInfoDouble(gSymbol, SYMBOL_POINT);

   hRsi   = iRSI(gSymbol, InpTf, InpRsiPeriod, PRICE_CLOSE);
   hTrend = iMA(gSymbol, InpTf, InpTrendEma, 0, MODE_EMA, PRICE_CLOSE);
   hAtr   = iATR(gSymbol, InpTf, InpAtrPeriod);
   if(hRsi == INVALID_HANDLE || hTrend == INVALID_HANDLE || hAtr == INVALID_HANDLE)
   { Print("Indicator creation failed: ", GetLastError()); return(INIT_FAILED); }

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippage);
   trade.SetTypeFillingBySymbol(gSymbol);

   int login = (int)AccountInfoInteger(ACCOUNT_LOGIN);
   gvBase = "HFTG_BASE_" + IntegerToString(login);
   gvHalt = "HFTG_HALT_" + IntegerToString(login);

   if(InpResetProtection)
   {
      GlobalVariableDel(gvBase);
      GlobalVariableDel(gvHalt);
      Print("Protection state reset.");
   }
   if(GlobalVariableCheck(gvBase))
      gBase = GlobalVariableGet(gvBase);
   else
   {
      gBase = AccountInfoDouble(ACCOUNT_BALANCE);
      GlobalVariableSet(gvBase, gBase);
   }
   permHalted = GlobalVariableCheck(gvHalt);
   dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   dayStamp = TimeToString(TimeCurrent(), TIME_DATE);
   dayHalted = false;

   PrintFormat("HFT_GOLDi v1.14 init: base=%.2f equity=%.2f halted=%s target=%.1fx",
               gBase, dayStartEquity, permHalted ? "YES" : "no", InpTargetMultiple);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   IndicatorRelease(hRsi);
   IndicatorRelease(hTrend);
   IndicatorRelease(hAtr);
   Comment("");
}

void OnTick()
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   string today = TimeToString(TimeCurrent(), TIME_DATE);
   if(today != dayStamp)
   {
      dayStamp = today;
      dayStartEquity = eq;
      dayHalted = false;
   }

   if(!permHalted && gBase > 0)
   {
      if(eq >= gBase * InpTargetMultiple)
      {
         CloseAll();
         permHalted = true;
         GlobalVariableSet(gvHalt, 1);
         Alert(StringFormat("TARGET REACHED: equity %.2f = %.1fx base %.2f. Trading stopped.", eq, InpTargetMultiple, gBase));
      }
      else if(eq <= gBase * (1.0 - InpMaxDrawdownPct / 100.0))
      {
         CloseAll();
         permHalted = true;
         GlobalVariableSet(gvHalt, 1);
         Alert(StringFormat("MAX DRAWDOWN PROTECTION: equity %.2f <= %.0f%% of base. EA halted.", eq, 100.0 - InpMaxDrawdownPct));
      }
   }
   if(!permHalted && !dayHalted && eq <= dayStartEquity * (1.0 - InpMaxDailyLossPct / 100.0))
   {
      CloseAll();
      dayHalted = true;
      Alert(StringFormat("DAILY LOSS LIMIT (%.0f%%): trading paused until next server day.", InpMaxDailyLossPct));
   }

   ManagePending();
   if(permHalted)
   { UpdateComment(eq); return; }

   ManagePositions();
   CheckMartingale();

   if(!InSession() && CountMyPositions() > 0)
      CloseAll();

   if(dayHalted || !InSession())
   { UpdateComment(eq); return; }

   datetime t0 = iTime(gSymbol, InpTf, 0);
   if(t0 == lastBar)
   { UpdateComment(eq); return; }
   lastBar = t0;

   if(InpEveryCandle)
   { EveryCandle(); UpdateComment(eq); return; }

   TryEnter();
   UpdateComment(eq);
}

bool InSession()
{
   MqlDateTime dt;
   TimeCurrent(dt);
   if(dt.day_of_week == 0 || dt.day_of_week == 6) return(false);
   if(InpStartHour <= InpEndHour)
      return(dt.hour >= InpStartHour && dt.hour < InpEndHour);
   return(dt.hour >= InpStartHour || dt.hour < InpEndHour);
}

bool IsManaged(long magic)
{
   return (magic == InpMagic || magic == 0);
}

int CountMyPositions()
{
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != gSymbol) continue;
      if(!IsManaged(PositionGetInteger(POSITION_MAGIC))) continue;
      n++;
   }
   return n;
}

bool HasPendingOrder(ulong &ticket)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong tk = OrderGetTicket(i);
      if(tk == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != gSymbol) continue;
      if(OrderGetInteger(ORDER_MAGIC) != InpMagic) continue;
      ticket = tk;
      return(true);
   }
   return(false);
}

void ManagePending()
{
   ulong tk = 0;
   if(!HasPendingOrder(tk)) return;
   if(permHalted || dayHalted || !InSession())
   {
      trade.OrderDelete(tk);
      Print("Pending limit cancelled (halt/session end)");
   }
}

void EveryCandle()
{
   if(gBase <= 0 || permHalted || dayHalted) return;
   ulong pt = 0;
   if(HasPendingOrder(pt)) trade.OrderDelete(pt);

   double tr[];
   if(CopyBuffer(hTrend, 0, 1, 1, tr) < 1) return;
   double cl[];
   if(CopyClose(gSymbol, InpTf, 1, 1, cl) < 1) return;
   int dir = 0;
   if(cl[0] > tr[0]) dir = 1;
   else if(cl[0] < tr[0]) dir = -1;
   else { gStatus = "flat: close==EMA50"; return; }

   MqlTick tick;
   if(!SymbolInfoTick(gSymbol, tick)) return;
   double spreadPrice = tick.ask - tick.bid;
   if(spreadPrice > InpMaxSpreadPts * 0.01)
   { gStatus = StringFormat("skip: spread $%.2f", spreadPrice); return; }

   int eaHeld = 0, eaHeldSide = 0, total = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetTicket(i) == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != gSymbol) continue;
      if(!IsManaged(PositionGetInteger(POSITION_MAGIC))) continue;
      total++;
      if(PositionGetInteger(POSITION_MAGIC) == InpMagic)
      {
         eaHeld++;
         eaHeldSide = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
      }
   }
   if(eaHeld > 0 && eaHeldSide == dir) { gStatus = "holding trend"; return; }
   if(total >= InpMaxMartPos)
   { gStatus = StringFormat("pool full %d/%d", total, InpMaxMartPos); return; }

   if(InpConfluence)
   {
      double rsiArr[];
      if(CopyBuffer(hRsi, 0, 0, 1, rsiArr) < 1) { gStatus = "skip: no RSI"; return; }
      double rsi = rsiArr[0];
      if(dir == 1 && rsi >= InpRsiUpFilter)
      { gStatus = StringFormat("hold out: RSI %.1f overbought (need < %.0f)", rsi, InpRsiUpFilter); return; }
      if(dir == -1 && rsi <= InpRsiDnFilter)
      { gStatus = StringFormat("hold out: RSI %.1f oversold (need > %.0f)", rsi, InpRsiDnFilter); return; }
   }

   double atr = AtrValue();
   if(atr <= 0) { gStatus = "skip: no ATR"; return; }

   if(InpSlopeFilter)
   {
      double emaArr[];
      if(CopyBuffer(hTrend, 0, 2, 2, emaArr) < 2) { gStatus = "skip: no EMA"; return; }
      bool rising = (emaArr[1] > emaArr[0]);
      if(dir == 1 && !rising) { gStatus = "hold out: EMA50 not rising"; return; }
      if(dir == -1 && rising) { gStatus = "hold out: EMA50 not falling"; return; }
   }

   if(InpZoneFilter)
   {
      double ema1[], cl1[];
      if(CopyBuffer(hTrend, 0, 1, 1, ema1) < 1) return;
      if(CopyClose(gSymbol, InpTf, 1, 1, cl1) < 1) return;
      double dist = cl1[0] - ema1[0];
      if(dir == 1 && dist > InpZoneAtr * atr)
      { gStatus = StringFormat("hold out: %.2f ATR above EMA50", dist / atr); return; }
      if(dir == -1 && -dist > InpZoneAtr * atr)
      { gStatus = StringFormat("hold out: %.2f ATR below EMA50", -dist / atr); return; }
   }

   double slDist = MathMax(MathRound(InpSL_Atr * atr / gPoint), 1) * gPoint;
   double tpDist = MathMax(MathRound(InpTP_Atr * atr / gPoint), 1) * gPoint;

   CloseAll();
   double price = (dir == 1) ? tick.ask : tick.bid;
   double sl = NormalizeDouble(dir == 1 ? price - slDist : price + slDist, gDigits);
   double tp = NormalizeDouble(dir == 1 ? price + tpDist : price - tpDist, gDigits);
   bool ok = (dir == 1) ? trade.Buy(InpEveryCandleLot, gSymbol, price, sl, tp, "HFTG")
                        : trade.Sell(InpEveryCandleLot, gSymbol, price, sl, tp, "HFTG");
   if(ok && trade.ResultRetcode() == TRADE_RETCODE_DONE)
   {
      gStatus = StringFormat("candle %s %.2f @ %.2f", dir == 1 ? "BUY" : "SELL", InpEveryCandleLot, price);
      PrintFormat("CANDLE %s %s @ %.2f SL %.2f TP %.2f (spread $%.2f)",
                  dir == 1 ? "BUY" : "SELL", gSymbol, price, sl, tp, spreadPrice);
   }
   else
      PrintFormat("Candle trade failed: retcode=%u %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
}

void CheckMartingale()
{
   if(gBase <= 0 || permHalted || dayHalted) return;
   if(!InpMartingale) return;
   if(!InSession()) return;

   MqlTick tick;
   if(!SymbolInfoTick(gSymbol, tick)) return;
   if((tick.ask - tick.bid) > InpMaxSpreadPts * 0.01) return;

   // per-side baskets: manual and EA trades managed even when on opposite sides
   for(int grp = 0; grp < 2; grp++)
   {
      int want = (grp == 0) ? 1 : -1;
      int n = 0, total = 0;
      ulong firstTicket = ULONG_MAX;
      double firstEntry = 0, firstSL = 0, firstTP = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0) continue;
         if(PositionGetString(POSITION_SYMBOL) != gSymbol) continue;
         if(!IsManaged(PositionGetInteger(POSITION_MAGIC))) continue;
         total++;
         int s = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
         if(s != want) continue;
         n++;
         if(ticket < firstTicket)
         {
            firstTicket = ticket;
            firstEntry = PositionGetDouble(POSITION_PRICE_OPEN);
            firstSL = PositionGetDouble(POSITION_SL);
            firstTP = PositionGetDouble(POSITION_TP);
         }
      }
      if(n == 0) continue;
      if(total >= InpMaxMartPos) return;   // shared pool full (manual + EA, max 3)

      // add one leg every $InpMartStepUsd against this side's FIRST entry
      bool add = (want == 1) ? (tick.bid <= firstEntry - InpMartStepUsd * n)
                             : (tick.ask >= firstEntry + InpMartStepUsd * n);
      if(!add)
      {
         gStatus = StringFormat("%s basket %d/%d legs (next add @ %.2f)",
                                want == 1 ? "long" : "short", n, InpMaxMartPos,
                                want == 1 ? firstEntry - InpMartStepUsd * n
                                          : firstEntry + InpMartStepUsd * n);
         continue;
      }

   // new leg uses the FIRST position's SL and TP (last leg uses the bigger lot)
      double lot = (n + 1 >= InpMaxMartPos) ? InpLastLegLot : InpMartLot;
      double price = (want == 1) ? tick.ask : tick.bid;
      double sl = firstSL, tp = firstTP;
      if(firstSL <= 0 || firstTP <= 0)
      {
         double atr = AtrValue();
         if(atr > 0)
         {
            double slDist = MathMax(MathRound(InpSL_Atr * atr / gPoint), 1) * gPoint;
            double tpDist = MathMax(MathRound(InpTP_Atr * atr / gPoint), 1) * gPoint;
            sl = NormalizeDouble(want == 1 ? price - slDist : price + slDist, gDigits);
            tp = NormalizeDouble(want == 1 ? price + tpDist : price - tpDist, gDigits);
         }
      }
      bool ok = (want == 1) ? trade.Buy(lot, gSymbol, price, sl, tp, "HFTG")
                            : trade.Sell(lot, gSymbol, price, sl, tp, "HFTG");
      if(ok && trade.ResultRetcode() == TRADE_RETCODE_DONE)
      {
         gStatus = StringFormat("martingale add %s %.2f (leg %d/%d, SL %.2f TP %.2f)",
                                want == 1 ? "BUY" : "SELL", lot, n + 1, InpMaxMartPos,
                                sl, tp);
         PrintFormat("MART %s %s %.2f @ %.2f (first %.2f SL %.2f TP %.2f)",
                     want == 1 ? "BUY" : "SELL", gSymbol, lot, price, firstEntry,
                     sl, tp);
      }
   }
}

void CloseAll()
{
   ulong tickets[];
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != gSymbol) continue;
      if(!IsManaged(PositionGetInteger(POSITION_MAGIC))) continue;
      ArrayResize(tickets, n + 1);
      tickets[n++] = ticket;
   }
   for(int i = 0; i < n; i++)
      trade.PositionClose(tickets[i]);
}

double AtrValue()
{
   double a[];
   if(CopyBuffer(hAtr, 0, 1, 1, a) < 1) return(0);
   return(a[0]);
}

void ManagePositions()
{
   double atr = AtrValue();
   if(atr <= 0) return;
   MqlTick tick;
   if(!SymbolInfoTick(gSymbol, tick)) return;

   // ---- ensure every managed position carries ATR SL/TP (manual trades have none) ----
   double slDist = MathMax(MathRound(InpSL_Atr * atr / gPoint), 1) * gPoint;
   double tpDist = MathMax(MathRound(InpTP_Atr * atr / gPoint), 1) * gPoint;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != gSymbol) continue;
      if(!IsManaged(PositionGetInteger(POSITION_MAGIC))) continue;
      double psl = PositionGetDouble(POSITION_SL);
      double ptp = PositionGetDouble(POSITION_TP);
      if(psl > 0 && ptp > 0) continue;
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      long ptype = PositionGetInteger(POSITION_TYPE);
      double nsl = psl, ntp = ptp;
      if(ptype == POSITION_TYPE_BUY)
      {
         if(psl <= 0) nsl = NormalizeDouble(open - slDist, gDigits);
         if(ptp <= 0) ntp = NormalizeDouble(open + tpDist, gDigits);
      }
      else
      {
         if(psl <= 0) nsl = NormalizeDouble(open + slDist, gDigits);
         if(ptp <= 0) ntp = NormalizeDouble(open - tpDist, gDigits);
      }
      if(psl <= 0 || ptp <= 0)
      {
         trade.PositionModify(ticket, nsl, ntp);
         PrintFormat("SET SL/TP ticket %s (open %.2f) SL %.2f TP %.2f",
                     IntegerToString(ticket), open, nsl, ntp);
      }
   }

   if(!InpTrailing) return;
   double bufferPts = ((tick.ask - tick.bid) / gPoint > InpHighSpreadPts)
                      ? InpTrailBufferHiPts : InpTrailBufferPts;
   double buffer = bufferPts * gPoint;

   // per-side baskets: each side trailed against its own weighted average entry
   for(int grp = 0; grp < 2; grp++)
   {
      int want = (grp == 0) ? 1 : -1;
      int n = 0;
      double totVol = 0, sumWe = 0;
      ulong tickets[];
      double sls[], tps[];
      long types[];
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0) continue;
         if(PositionGetString(POSITION_SYMBOL) != gSymbol) continue;
         if(!IsManaged(PositionGetInteger(POSITION_MAGIC))) continue;
         int s = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
         if(s != want) continue;
         double v = PositionGetDouble(POSITION_VOLUME);
         totVol += v;
         sumWe += PositionGetDouble(POSITION_PRICE_OPEN) * v;
         ArrayResize(tickets, n + 1);
         ArrayResize(sls, n + 1);
         ArrayResize(tps, n + 1);
         ArrayResize(types, n + 1);
         tickets[n] = ticket;
         sls[n] = PositionGetDouble(POSITION_SL);
         tps[n] = PositionGetDouble(POSITION_TP);
         types[n] = PositionGetInteger(POSITION_TYPE);
         n++;
      }
      if(n == 0) continue;

      double avgEntry = sumWe / totVol;
      double netUsd = (want == 1 ? (tick.bid - avgEntry) : (avgEntry - tick.ask)) * totVol * 100.0;
      if(netUsd < InpBeAtr * atr)
      {
         gStatus = StringFormat("%s basket %d leg(s) net $%.2f (trail at +$%.2f)",
                                want == 1 ? "long" : "short", n, netUsd, InpBeAtr * atr);
         continue;
      }

      for(int i = 0; i < n; i++)
      {
         double sl = sls[i], tp = tps[i];
         long type = types[i];
         double ns = sl;
         if(buffer > 0)
         {
            if(type == POSITION_TYPE_BUY)
            {
               double trail = tick.bid - buffer;
               if(trail < avgEntry) trail = avgEntry;
               if(trail > sl + gPoint / 2.0) ns = trail;
            }
            else
            {
               double trail = tick.ask + buffer;
               if(trail > avgEntry) trail = avgEntry;
               if(sl == 0 || trail < sl - gPoint / 2.0) ns = trail;
            }
         }
         else if(type == POSITION_TYPE_BUY)
         {
            if(avgEntry > sl + gPoint / 2.0) ns = avgEntry;
         }
         else
         {
            if(sl == 0 || avgEntry < sl - gPoint / 2.0) ns = avgEntry;
         }
         if((type == POSITION_TYPE_BUY && ns > sl + gPoint / 2.0) ||
            (type == POSITION_TYPE_SELL && (sl == 0 || ns < sl - gPoint / 2.0)))
            trade.PositionModify(tickets[i], NormalizeDouble(ns, gDigits), tp);
      }
      gStatus = StringFormat("trailing %s basket %d leg(s) net $%.2f buffer %.2f",
                             want == 1 ? "long" : "short", n, netUsd, buffer);
   }
}

double CalcLots(double &slDist, double &tpDist, ENUM_ORDER_TYPE type, double price, double atrNow)
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double point    = gPoint;
   double tickSize = SymbolInfoDouble(gSymbol, SYMBOL_TRADE_TICK_SIZE);
   double tickVal  = SymbolInfoDouble(gSymbol, SYMBOL_TRADE_TICK_VALUE);
   double minL = SymbolInfoDouble(gSymbol, SYMBOL_VOLUME_MIN);
   double maxL = SymbolInfoDouble(gSymbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(gSymbol, SYMBOL_VOLUME_STEP);
   if(tickSize <= 0 || tickVal <= 0 || step <= 0 || slDist <= 0 || atrNow <= 0) return(0);

   double perLotPt = (point / tickSize) * tickVal;
   double slPts = slDist / point;
   double riskLots = (eq * InpRiskPercent / 100.0) / (slPts * perLotPt);
   double lots = 0;

   if(riskLots >= minL)
   {
      lots = MathFloor(riskLots / step + 1e-9) * step;
      if(lots > maxL) lots = maxL;
   }
   else
   {
      double affPts = (eq * InpMaxEffectiveRiskPct / 100.0) / (minL * perLotPt);
      if(slPts > affPts)
      {
         double minSlPts = InpShrinkMinAtr * atrNow / point;
         if(affPts < minSlPts)
         {
            gStatus = StringFormat("WAIT equity>=$%.2f for 0.01 lot (SL %.0f pts)",
                                   minSlPts * minL * perLotPt / (InpMaxEffectiveRiskPct / 100.0), minSlPts);
            return(0);
         }
         double orig = slPts;
         slPts = affPts;
         slDist = slPts * point;
         tpDist = tpDist * (slPts / orig);
      }
      lots = minL;
   }

   double need = 0;
   if(OrderCalcMargin(type, gSymbol, lots, price, need))
   {
      double free = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
      int guard = 0;
      while(need > free * 0.85 && lots - step >= minL && guard++ < 500)
      {
         lots = MathFloor((lots - step) / step + 1e-9) * step;
         if(!OrderCalcMargin(type, gSymbol, lots, price, need)) return(0);
      }
      if(need > free * 0.85) return(0);
   }
   return(NormalizeDouble(lots, 2));
}

void TryEnter()
{
   if(gBase <= 0 || permHalted || dayHalted) return;
   if(CountMyPositions() >= InpMaxPositions) return;
   if(!InSession()) return;
   ulong ptk = 0;
   if(HasPendingOrder(ptk)) { gStatus = "limit order resting"; return; }

   MqlTick tick;
   if(!SymbolInfoTick(gSymbol, tick)) return;
   double spreadPrice = tick.ask - tick.bid;
   if(spreadPrice > InpMaxSpreadPts * 0.01)
   { gStatus = StringFormat("skip: spread $%.2f > $%.2f", spreadPrice, InpMaxSpreadPts * 0.01); return; }

   double r[], tr[], a[], cl[];
   if(CopyBuffer(hRsi,   0, 1, 2, r)   < 2) return;
   if(CopyBuffer(hTrend, 0, 1, 2, tr)  < 2) return;
   if(CopyBuffer(hAtr,   0, 1, 1, a)   < 1) return;
   if(CopyClose(gSymbol, InpTf, 1, 2, cl) < 2) return;

   // signal on last closed bar (index 0 of copied arrays == bar 1)
   bool buy  = (r[1] < InpRsiLo && r[0] >= InpRsiLo && cl[0] > tr[0]);
   bool sell = (r[1] > InpRsiHi && r[0] <= InpRsiHi && cl[0] < tr[0]);
   if(!buy && !sell)
   { gStatus = "waiting for signal"; return; }

   double atr1 = a[0];
   if(atr1 <= 0) return;

   double slDist = MathMax(MathRound(InpSL_Atr * atr1 / gPoint), 1) * gPoint;
   double tpDist = MathMax(MathRound(InpTP_Atr * atr1 / gPoint), 1) * gPoint;

   double price = buy ? tick.ask : tick.bid;
   ENUM_ORDER_TYPE type = buy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;

   double lots = CalcLots(slDist, tpDist, type, price, atr1);
   if(lots <= 0)
   {
      if(gStatus == "") gStatus = "skip: sizing";
      return;
   }
   gStatus = StringFormat("trading, lots %.2f", lots);

   double sl = buy ? price - slDist : price + slDist;
   double tp = buy ? price + tpDist : price - tpDist;
   sl = NormalizeDouble(sl, gDigits);
   tp = NormalizeDouble(tp, gDigits);

   if(InpUseLimitEntry)
   {
      double px = NormalizeDouble(cl[0], gDigits);
      double stops = (double)SymbolInfoInteger(gSymbol, SYMBOL_TRADE_STOPS_LEVEL);
      if(buy && px >= tick.bid - stops * gPoint)
      { gStatus = "limit not below market"; return; }
      if(!buy && px <= tick.ask + stops * gPoint)
      { gStatus = "limit not above market"; return; }
      double lsl = NormalizeDouble(buy ? px - slDist : px + slDist, gDigits);
      double ltp = NormalizeDouble(buy ? px + tpDist : px - tpDist, gDigits);
      bool ok = buy ? trade.BuyLimit(lots, px, gSymbol, lsl, ltp, ORDER_TIME_GTC, 0, "HFTG")
                    : trade.SellLimit(lots, px, gSymbol, lsl, ltp, ORDER_TIME_GTC, 0, "HFTG");
      if(ok && trade.ResultRetcode() == TRADE_RETCODE_DONE)
         PrintFormat("LIMIT %s %.2f %s @ %.2f SL %.2f TP %.2f (spread $%.2f)",
                     buy ? "BUY" : "SELL", lots, gSymbol, px, lsl, ltp, spreadPrice);
      else
         PrintFormat("Limit failed: retcode=%u %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
      return;
   }

   bool ok = buy ? trade.Buy(lots, gSymbol, price, sl, tp, "HFTG")
                 : trade.Sell(lots, gSymbol, price, sl, tp, "HFTG");
   if(ok && trade.ResultRetcode() == TRADE_RETCODE_DONE)
      PrintFormat("%s %.2f %s @ %.2f SL %.2f TP %.2f (spread $%.2f)",
                  buy ? "BUY" : "SELL", lots, gSymbol, price, sl, tp, spreadPrice);
   else
      PrintFormat("Order failed: retcode=%u %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
}

void UpdateComment(double eq)
{
   double pct = gBase > 0 ? eq / gBase * 100.0 : 0;
   string state = permHalted ? "HALTED (target/drawdown)" : (dayHalted ? "PAUSED (daily limit)" : "ACTIVE");
   Comment(StringFormat("HFT_GOLDi v1.14 | base %.2f | equity %.2f | %.0f%% of %.0fx | %s\n%s",
                        gBase, eq, pct, InpTargetMultiple, state, gStatus));
}
