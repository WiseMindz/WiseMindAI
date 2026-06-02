//+------------------------------------------------------------------+
//|  WiseMind Bridge EA v1.0                                         |
//|  Auto-executes trades from WiseMind Python bot signal files      |
//|                                                                  |
//|  Supports: Wise London v1.0 + Wise NY v2.0                       |
//|  Assets:   EURUSD, XAUUSD, CHFJPY (and any other)               |
//|  Sessions: London 09:00–11:15 | NY 14:00–17:00 (CEST)           |
//|                                                                  |
//|  HOW IT WORKS:                                                   |
//|  1. Attach this EA to ANY chart (EURUSD 5m recommended)          |
//|  2. Python bot writes wisemind_TIMESTAMP.txt to Files\wisemind\  |
//|  3. EA polls every 500ms, reads file, executes trade, deletes    |
//|                                                                  |
//|  INSTALL:                                                        |
//|  Copy to MT5 → File → Open Data Folder → MQL5/Experts/          |
//|  Compile in MetaEditor (F7), then attach to chart                |
//+------------------------------------------------------------------+
#property copyright "WiseMind AI"
#property version   "1.00"
#property description "WiseMind auto-execution bridge — reads signal files from Python bot"

#include <Trade\Trade.mqh>

//── Inputs ────────────────────────────────────────────────────────────────────
input bool   InpEnableTrading  = false;       // Enable Trade Execution (false = dry run)
input int    InpPollMs         = 500;         // Poll interval (milliseconds)
input int    InpSlippage       = 10;          // Max slippage (points)
input int    InpMagicNumber    = 20260101;    // Magic number for WiseMind trades
input bool   InpLogAll         = true;        // Log all activity to Experts tab

//── Globals ───────────────────────────────────────────────────────────────────
CTrade g_trade;
string g_folder = "wisemind\\";   // Subfolder inside MT5 Files directory

//+------------------------------------------------------------------+
//| EA Initialization                                                  |
//+------------------------------------------------------------------+
int OnInit()
{
    g_trade.SetExpertMagicNumber(InpMagicNumber);
    g_trade.SetDeviationInPoints(InpSlippage);
    g_trade.SetTypeFilling(ORDER_FILLING_IOC);

    EventSetMillisecondTimer(InpPollMs);

    // Ensure signals folder exists
    FolderCreate(g_folder);

    Print("════════════════════════════════════════");
    Print("  WiseMind Bridge EA v1.0 — STARTED");
    Print("  Trading: ", InpEnableTrading ? "ENABLED ✅" : "DRY RUN 🔬");
    Print("  Signals folder: Files\\", g_folder);
    Print("  Poll interval: ", InpPollMs, "ms");
    Print("  Magic: ", InpMagicNumber);
    Print("════════════════════════════════════════");

    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| EA Deinitialization                                                |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    EventKillTimer();
    Print("WiseMind Bridge EA stopped.");
}

//+------------------------------------------------------------------+
//| Timer — main poll loop                                             |
//+------------------------------------------------------------------+
void OnTimer()
{
    ProcessSignalFiles();
}

//+------------------------------------------------------------------+
//| Scan and process all pending signal files                         |
//+------------------------------------------------------------------+
void ProcessSignalFiles()
{
    string filename = "";
    long   search   = FileFindFirst(g_folder + "wisemind_*.txt", filename);
    if(search == INVALID_HANDLE) return;

    do
    {
        string fullpath = g_folder + filename;
        if(InpLogAll) Print("📄 Signal file found: ", filename);

        // Parse
        string sym = "", side = "", sess = "", grade = "", comment = "";
        double lot = 0, sl = 0, tp = 0;

        bool parsed = ParseSignalFile(fullpath, sym, side, lot, sl, tp, sess, grade, comment);

        if(parsed)
        {
            if(InpLogAll)
                Print("📊 Parsed — ", side, " ", lot, " ", sym,
                      " SL:", sl, " TP:", tp,
                      " Session:", sess, " Grade:", grade);

            ExecuteSignal(sym, side, lot, sl, tp, comment);
        }
        else
        {
            Print("❌ Parse failed for: ", filename);
        }

        // Always delete after processing (success or fail)
        FileDelete(fullpath);
        if(InpLogAll) Print("🗑️  Signal file deleted: ", filename);

    } while(FileFindNext(search, filename));

    FileFindClose(search);
}

//+------------------------------------------------------------------+
//| Parse key=value signal file                                       |
//+------------------------------------------------------------------+
bool ParseSignalFile(string path,
                     string &sym, string &side,
                     double &lot, double &sl, double &tp,
                     string &sess, string &grade, string &comment)
{
    int handle = FileOpen(path, FILE_READ | FILE_TXT | FILE_ANSI, '\n');
    if(handle == INVALID_HANDLE)
    {
        Print("Cannot open file: ", path, " Error: ", GetLastError());
        return false;
    }

    while(!FileIsEnding(handle))
    {
        string line = FileReadString(handle);
        StringTrimLeft(line);
        StringTrimRight(line);
        if(StringLen(line) == 0) continue;

        int sep = StringFind(line, "=");
        if(sep < 0) continue;

        string key = StringSubstr(line, 0, sep);
        string val = StringSubstr(line, sep + 1);

        if(key == "SYMBOL")  sym     = val;
        if(key == "SIDE")    side    = val;
        if(key == "LOT")     lot     = StringToDouble(val);
        if(key == "SL")      sl      = StringToDouble(val);
        if(key == "TP")      tp      = StringToDouble(val);
        if(key == "SESSION") sess    = val;
        if(key == "GRADE")   grade   = val;
        if(key == "COMMENT") comment = val;
    }

    FileClose(handle);

    // Validate required fields
    if(sym == "" || side == "" || lot <= 0 || sl <= 0 || tp <= 0)
    {
        Print("❌ Invalid signal data: sym='", sym, "' side='", side,
              "' lot=", lot, " sl=", sl, " tp=", tp);
        return false;
    }

    return true;
}

//+------------------------------------------------------------------+
//| Execute the trade (or dry-run log it)                             |
//+------------------------------------------------------------------+
void ExecuteSignal(string sym, string side, double lot,
                   double sl, double tp, string comment)
{
    if(!InpEnableTrading)
    {
        Print("🔬 DRY RUN — would execute: ", side, " ", lot, " ", sym,
              " SL:", sl, " TP:", tp, " | ", comment);
        return;
    }

    // Check trading is allowed
    if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
    {
        Print("❌ Trading not allowed by terminal (check AutoTrading button)");
        return;
    }
    if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
    {
        Print("❌ EA trading not allowed — enable in EA settings");
        return;
    }

    bool result = false;

    if(side == "LONG")
    {
        result = g_trade.Buy(lot, sym, 0, sl, tp, comment);
    }
    else if(side == "SHORT")
    {
        result = g_trade.Sell(lot, sym, 0, sl, tp, comment);
    }
    else
    {
        Print("❌ Unknown side: '", side, "' — expected LONG or SHORT");
        return;
    }

    if(result)
    {
        Print("✅ EXECUTED: ", side, " ", lot, " ", sym,
              " @ ", g_trade.ResultPrice(),
              " SL:", sl, " TP:", tp,
              " Ticket#", g_trade.ResultOrder());
    }
    else
    {
        Print("❌ FAILED: ", side, " ", sym,
              " RetCode:", g_trade.ResultRetcode(),
              " — ", g_trade.ResultRetcodeDescription());
    }
}

//+------------------------------------------------------------------+
//| OnTick — fallback (EA also fires on price tick)                   |
//+------------------------------------------------------------------+
void OnTick()
{
    // Primary polling is via timer — this is a safety fallback
}
//+------------------------------------------------------------------+
