-- SpotiWoW-Raven for Turtle WoW / WoW 1.12.1 (Lua 5.0 + SuperWoW)
-- Bridge files live in the client's Imports folder:
--   Python -> addon: ImportFile("SpotifyNowState")
--   addon -> Python: ExportFile("SpotifyNowCommand", payload)
-- No chat-command injection, pixel strip, or screen capture is needed.

local CHANNELS = {
    say = "SAY", yell = "YELL", party = "PARTY",
    guild = "GUILD", raid = "RAID", emote = "EMOTE",
}

-- command names understood by the Python companion
local CMD = {
    prev = "prev", pause = "pause", next = "next", back = "back",
    fwd = "fwd", voldown = "voldown", volup = "volup",
}

local playing = false
local volume = -1
local SendCommand
local lastLyricsModeSeen = nil
local Locale = SPOTIWOW_RAVEN_L or {}

local function T(key)
    return Locale[key] or key
end

local function Print(msg)
    DEFAULT_CHAT_FRAME:AddMessage("|cff1ed760[Spotify]|r " .. msg)
end

local function NowPlaying()
    if SpotifyNowDB.title and SpotifyNowDB.title ~= "" then
        return SpotifyNowDB.artist .. " - " .. SpotifyNowDB.title
    end
    return nil
end

local function Announce(channelKey)
    local np = NowPlaying()
    if not np then
        Print(T("no_track"))
        return
    end
    local chan = CHANNELS[channelKey]
    if chan == "EMOTE" then
        SendChatMessage(T("announce_emote_prefix") .. np, "EMOTE")
    else
        SendChatMessage(T("announce_prefix") .. np .. " ~", chan)
    end
end

local function SingLine(text)
    if not SpotifyNowDB.lyrics or text == "" then return end
    local chan = CHANNELS[SpotifyNowDB.channel] or "SAY"
    if chan == "EMOTE" then
        SendChatMessage(T("sing_emote_prefix") .. text .. "\"", "EMOTE")
    else
        SendChatMessage("~ " .. text .. " ~", chan)
    end
end

local function PrintLyricsMode(on)
    -- Local-only feedback in the default chat frame. This does NOT call
    -- SendChatMessage and is never sent to SAY/PARTY/GUILD/RAID or other players.
    if on then
        Print(T("lyrics_mode") .. "|cff00ff00ON|r")
    else
        Print(T("lyrics_mode") .. "|cffff0000OFF|r")
    end
end

local function SetLyrics(on, syncToCompanion)
    on = not not on
    local changed = SpotifyNowDB.lyrics ~= on
    SpotifyNowDB.lyrics = on
    -- Pre-seed the observed state to avoid a duplicate when Python echoes it
    -- through ImportFile. The global hotkey changes Python state directly and
    -- is announced by PollBridgeState below, without any chat command.
    lastLyricsModeSeen = on
    if changed then PrintLyricsMode(on) end
    if syncToCompanion then SendCommand("lyrics", on and "1" or "0") end
end

----------------------------------------------------------------------
-- Addon -> companion bridge: SuperWoW ExportFile into client\imports.
-- The game auto-appends .txt to the file base name.
----------------------------------------------------------------------
local commandSequence = 0
local commandSession = floor((GetTime() or 0) * 1000)
local commandWriteWarningShown = false

SendCommand = function(cmd, value)
    if type(ExportFile) ~= "function" then
        if not commandWriteWarningShown then
            Print(T("export_missing"))
            commandWriteWarningShown = true
        end
        return
    end
    commandSequence = commandSequence + 1
    local payload = "SPNC1|" .. commandSession .. "|" .. commandSequence .. "|" .. cmd .. "|" .. (value or "")
    local ok = pcall(ExportFile, "SpotifyNowCommand", payload)
    if not ok and not commandWriteWarningShown then
        Print(T("command_write_failed"))
        commandWriteWarningShown = true
    end
end

----------------------------------------------------------------------
-- Mini player
----------------------------------------------------------------------
local ui = CreateFrame("Frame", "SpotifyNowFrame", UIParent)
ui:SetWidth(250)
ui:SetHeight(58)
ui:SetPoint("CENTER", UIParent, "CENTER", 0, -200)
ui:SetFrameStrata("MEDIUM")
ui:SetMovable(true)
ui:EnableMouse(true)
ui:SetClampedToScreen(true)
ui:RegisterForDrag("LeftButton")
ui:SetBackdrop({
    bgFile = "Interface\\Tooltips\\UI-Tooltip-Background",
    edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
    tile = true, tileSize = 16, edgeSize = 12,
    insets = { left = 3, right = 3, top = 3, bottom = 3 },
})
ui:SetBackdropColor(0, 0, 0, 0.85)
ui:SetBackdropBorderColor(0.12, 0.84, 0.38, 1)
ui:SetScript("OnDragStart", function() this:StartMoving() end)
ui:SetScript("OnDragStop", function()
    this:StopMovingOrSizing()
    local p, _, rp, x, y = this:GetPoint()
    SpotifyNowDB.pos = { p, rp, x, y }
end)

local titleText = ui:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
titleText:SetPoint("TOPLEFT", ui, "TOPLEFT", 8, -8)
titleText:SetWidth(180)
titleText:SetJustifyH("LEFT")

local volText = ui:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
volText:SetPoint("TOPRIGHT", ui, "TOPRIGHT", -8, -8)
volText:SetJustifyH("RIGHT")

local function MakeButton(label, tip, w, x, cmd)
    local b = CreateFrame("Button", "SpotifyNowBtn" .. cmd, ui, "UIPanelButtonTemplate")
    b:SetWidth(w)
    b:SetHeight(20)
    b:SetPoint("BOTTOMLEFT", ui, "BOTTOMLEFT", x, 8)
    b:SetText(label)
    b:SetScript("OnClick", function() SendCommand(cmd) end)
    b:SetScript("OnEnter", function()
        GameTooltip:SetOwner(this, "ANCHOR_TOP")
        GameTooltip:SetText(tip)
        GameTooltip:Show()
    end)
    b:SetScript("OnLeave", function() GameTooltip:Hide() end)
    return b
end

MakeButton("<<", T("previous"), 30, 8, CMD.prev)
local playBtn = MakeButton(">", T("play_pause"), 30, 40, CMD.pause)
MakeButton(">>", T("next"), 30, 72, CMD.next)
MakeButton("-10", T("back_10"), 32, 108, CMD.back)
MakeButton("+10", T("forward_10"), 32, 142, CMD.fwd)
MakeButton("V-", T("volume_down"), 28, 180, CMD.voldown)
MakeButton("V+", T("volume_up"), 28, 210, CMD.volup)

-- Character-based marquee: safe for the legacy WoW 1.12 client, without
-- relying on newer FontString clipping APIs that may not exist in this client.
local TITLE_VISIBLE_CHARS = 27
local TITLE_SCROLL_STEP = 0.28
local titleScrollSource = nil
local titleScrollOffset = 1
local titleScrollElapsed = 0

local function RefreshTitleText()
    if not titleScrollSource or titleScrollSource == "" then
        titleText:SetText(T("waiting"))
        return
    end
    if strlen(titleScrollSource) <= TITLE_VISIBLE_CHARS then
        titleText:SetText(titleScrollSource)
        return
    end
    local cycle = titleScrollSource .. "     "
    local cycleLength = strlen(cycle)
    local display = strsub(cycle, titleScrollOffset, titleScrollOffset + TITLE_VISIBLE_CHARS - 1)
    if strlen(display) < TITLE_VISIBLE_CHARS then
        display = display .. strsub(cycle, 1, TITLE_VISIBLE_CHARS - strlen(display))
    end
    titleText:SetText(display)
    titleScrollOffset = titleScrollOffset + 1
    if titleScrollOffset > cycleLength then titleScrollOffset = 1 end
end

local function RefreshUI()
    local np = NowPlaying()
    if np ~= titleScrollSource then
        titleScrollSource = np or ""
        titleScrollOffset = 1
        titleScrollElapsed = 0
        RefreshTitleText()
    end
    if playing then playBtn:SetText("II") else playBtn:SetText(">") end
    if volume >= 0 then volText:SetText(T("volume_label") .. " " .. volume) else volText:SetText(T("volume_label") .. " --") end
end

local function Help()
    Print(T("help_1"))
    Print(T("help_2"))
    Print(T("help_3"))
    Print(T("help_4"))
    Print(T("help_5"))
end

SLASH_SPOTIFYNOW1 = "/spn"
SLASH_SPOTIFYNOW2 = "/spotify"
SlashCmdList["SPOTIFYNOW"] = function(msg)
    msg = msg or ""
    local _, _, cmd, rest = strfind(msg, "^(%S*)%s*(.*)$")
    cmd = strlower(cmd or "")
    rest = rest or ""

    if cmd == "" or cmd == "show" then
        local np = NowPlaying()
        if np then Print(np) else Print(T("no_track")) end

    elseif CHANNELS[cmd] then
        Announce(cmd)

    elseif CMD[cmd] then
        SendCommand(CMD[cmd])

    elseif cmd == "ui" then
        SpotifyNowDB.ui = not SpotifyNowDB.ui
        if SpotifyNowDB.ui then ui:Show() else ui:Hide() end

    elseif cmd == "lyrics" then
        local arg = strlower(rest)
        if arg == "on" then SetLyrics(true, true)
        elseif arg == "off" then SetLyrics(false, true)
        else SetLyrics(not SpotifyNowDB.lyrics, true) end

    elseif cmd == "channel" then
        local arg = strlower(rest)
        if CHANNELS[arg] then
            SpotifyNowDB.channel = arg
            Print(T("lyrics_channel_prefix") .. arg)
        else
            Print(T("channels_available"))
        end

    else
        Help()
    end
end

----------------------------------------------------------------------
-- Python -> addon state reader. Protocol fields are pipe-separated; text fields
-- are URL-percent-encoded by Python so delimiters cannot corrupt the record.
----------------------------------------------------------------------
local lastStateSequence = nil
local lastLyricsSequence = nil
local statePollElapsed = 0
local importWarningShown = false

local function DecodeField(value)
    value = value or ""
    value = gsub(value, "%%(%x%x)", function(hex)
        return strchar(tonumber(hex, 16))
    end)
    return value
end

local function SplitState(payload)
    local fields = {}
    local startAt = 1
    for i = 1, 11 do
        local stopAt = strfind(payload, "|", startAt, true)
        if not stopAt then return nil end
        fields[i] = strsub(payload, startAt, stopAt - 1)
        startAt = stopAt + 1
    end
    fields[12] = strsub(payload, startAt)
    return fields
end

local function PollBridgeState()
    if not SpotifyNowDB then return end
    if type(ImportFile) ~= "function" then
        if not importWarningShown then
            Print(T("import_missing"))
            importWarningShown = true
        end
        return
    end
    local ok, payload = pcall(ImportFile, "SpotifyNowState")
    if not ok or type(payload) ~= "string" or payload == "" then return end
    payload = gsub(payload, "[\r\n]+$", "")
    local fields = SplitState(payload)
    if not fields or fields[1] ~= "SPN1" then return end

    local stateSequence = tonumber(fields[2])
    if not stateSequence or stateSequence == lastStateSequence then return end
    lastStateSequence = stateSequence

    SpotifyNowDB.artist = DecodeField(fields[4])
    SpotifyNowDB.title = DecodeField(fields[5])
    playing = fields[8] == "1"
    volume = tonumber(fields[9]) or -1

    -- Ctrl+Alt+L toggles Lyrics in the Python companion. Announce only actual
    -- changes in the in-game system chat; the first state read is a baseline,
    -- not a user action. SetLyrics() pre-seeds this value for slash commands,
    -- preventing duplicate messages when Python confirms the same state.
    local bridgeLyrics = fields[10] == "1"
    if lastLyricsModeSeen == nil then
        lastLyricsModeSeen = bridgeLyrics
    elseif bridgeLyrics ~= lastLyricsModeSeen then
        lastLyricsModeSeen = bridgeLyrics
        PrintLyricsMode(bridgeLyrics)
    end
    SpotifyNowDB.lyrics = bridgeLyrics
    RefreshUI()

    local lyricSequence = tonumber(fields[11])
    if lyricSequence then
        if lastLyricsSequence == nil then
            -- Seed the sequence on first read; don't replay a stale line on login.
            lastLyricsSequence = lyricSequence
        elseif lyricSequence ~= lastLyricsSequence then
            lastLyricsSequence = lyricSequence
            local lyric = DecodeField(fields[12])
            if lyric ~= "" then SingLine(lyric) end
        end
    end
end

local statePoller = CreateFrame("Frame", "SpotifyNowStatePoller")
statePoller:SetScript("OnUpdate", function()
    local elapsed = arg1 or 0
    statePollElapsed = statePollElapsed + elapsed
    if statePollElapsed >= 0.25 then
        statePollElapsed = 0
        PollBridgeState()
    end
    if titleScrollSource and strlen(titleScrollSource) > TITLE_VISIBLE_CHARS then
        titleScrollElapsed = titleScrollElapsed + elapsed
        if titleScrollElapsed >= TITLE_SCROLL_STEP then
            titleScrollElapsed = titleScrollElapsed - TITLE_SCROLL_STEP
            RefreshTitleText()
        end
    end
end)

local frame = CreateFrame("Frame")
frame:RegisterEvent("ADDON_LOADED")
frame:SetScript("OnEvent", function()
    if event == "ADDON_LOADED" and arg1 == "SpotiWoW-Raven" then
        if not SpotifyNowDB then SpotifyNowDB = {} end
        if SpotifyNowDB.artist == nil then SpotifyNowDB.artist = "" end
        if SpotifyNowDB.title == nil then SpotifyNowDB.title = "" end
        if SpotifyNowDB.channel == nil then SpotifyNowDB.channel = "say" end
        if SpotifyNowDB.ui == nil then SpotifyNowDB.ui = true end
        -- Lyrics mode is synchronized from the Python state file.
        if SpotifyNowDB.pos then
            ui:ClearAllPoints()
            ui:SetPoint(SpotifyNowDB.pos[1], UIParent, SpotifyNowDB.pos[2],
                SpotifyNowDB.pos[3], SpotifyNowDB.pos[4])
        end
        if not SpotifyNowDB.ui then ui:Hide() end
        RefreshUI()
        Print(T("loaded"))
    end
end)
