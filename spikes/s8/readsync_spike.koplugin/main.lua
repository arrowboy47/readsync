-- readsync spike plugin (S8 anchor resolution, S10 follow-along). Throwaway: delete this folder to remove it.
local DataStorage = require("datastorage")
local InfoMessage = require("ui/widget/infomessage")
local UIManager = require("ui/uimanager")
local WidgetContainer = require("ui/widget/container/widgetcontainer")
local json = require("json")
local logger = require("logger")
local lfs = require("libs/libkoreader-lfs")
local NetworkMgr = require("ui/network/manager")
local _ = require("gettext")

local DIR = DataStorage:getDataDir() .. "/plugins/readsync_spike.koplugin/"
local OUT = DataStorage:getDataDir() .. "/readsync_spike_out/"

local Spike = WidgetContainer:extend{ name = "readsync_spike", is_doc_only = false }

local function norm(s)
    s = s:gsub("\194\173", "")           -- soft hyphen
    s = s:gsub("\194\160", " ")          -- nbsp
    s = s:gsub("%s+", " ")
    return (s:gsub("^ ", ""):gsub(" $", ""))
end

local function readfile(p) local f = io.open(p, "rb"); if not f then return nil end local d = f:read("*a"); f:close(); return d end
local function writefile(p, d) lfs.mkdir(OUT); local f = assert(io.open(p, "wb")); f:write(d); f:close() end

function Spike:init() self.ui.menu:registerToMainMenu(self) end

function Spike:addToMainMenu(items)
    items.readsync_spike = {
        text = _("Readsync spike"),
        sorting_hint = "more_tools",
        sub_item_table = {
            { text = _("S8: resolve 20 anchors (open book)"), callback = function() self:runS8() end },
            { text = _("S8: apply first resolved anchor as highlight (A16)"), callback = function() self:applyLive() end },
            { text = _("S8: remove spike highlights"), callback = function() self:removeSpike() end },
            { text = _("S10: start follow-along (30 min)"), callback = function() self:startS10() end },
            { text = _("S10: stop follow-along"), callback = function() self:stopS10() end },
        },
    }
end

function Spike:runS8()
    local doc = self.ui.document
    if not (doc and self.ui.rolling) then return UIManager:show(InfoMessage:new{ text = "Open the EPUB first" }) end
    local data = json.decode(readfile(DIR .. "samples.json") or "{}")
    if not data.samples then return UIManager:show(InfoMessage:new{ text = "samples.json missing" }) end
    local res, exact = {}, 0
    local t0 = os.time()
    for _, s in ipairs(data.samples) do
        local r = { id = s.id, spine_index = s.spine_index, flags = s.flags, quote = s.quote }
        local ok, hits = pcall(function() return doc:findAllText(s.quote, false, 0, 50, false) end)
        if not ok then r.error = tostring(hits)
        else
            r.hits_total = hits and #hits or 0
            local frag = string.format("/body/DocFragment[%d]", s.spine_index + 1)
            local mine = {}
            for _, h in ipairs(hits or {}) do
                if h.start and h.start:find(frag, 1, true) == 1 then mine[#mine + 1] = h end
            end
            r.hits_in_fragment = #mine
            local h = mine[1]
            if not h then
                -- fallback (soft hyphens, E6): find the first and last few words separately and join them
                local words = {}
                for w in s.quote:gmatch("%S+") do words[#words + 1] = w end
                for _, k in ipairs({ 3, 2, 1 }) do
                    if #words > 2 * k then
                        local A = table.concat(words, " ", 1, k)
                        local B = table.concat(words, " ", #words - k + 1, #words)
                        local ha = doc:findAllText(A, false, 0, 50, false) or {}
                        local hb = doc:findAllText(B, false, 0, 50, false) or {}
                        for _, a in ipairs(ha) do
                            if a.start:find(frag, 1, true) == 1 then
                                for _, b in ipairs(hb) do
                                    if b.start:find(frag, 1, true) == 1 and doc:getTextFromXPointers(a.start, b["end"]) then
                                        local t = norm(doc:getTextFromXPointers(a.start, b["end"]))
                                        if t == norm(s.quote) then h = { start = a.start, ["end"] = b["end"] }; r.fallback = k; break end
                                    end
                                end
                            end
                            if h then break end
                        end
                    end
                    if h then break end
                end
            end
            if h then
                r.pos0, r.pos1 = h.start, h["end"]
                local txt = doc:getTextFromXPointers(h.start, h["end"])
                r.text = txt and norm(txt) or nil
                r.exact = (r.text == norm(s.quote))
                if r.exact then exact = exact + 1 end
            end
        end
        res[#res + 1] = r
        self.last = self.last or {}
        if r.exact and not self.first then self.first = r end
    end
    local rep = { book = data.book, doc_path = doc.file, koreader = require("version"):getCurrentRevision(),
                  seconds = os.time() - t0, exact = exact, total = #data.samples, results = res }
    writefile(OUT .. "s8_result.json", json.encode(rep))
    UIManager:show(InfoMessage:new{ text = string.format("S8: %d/%d exact in %ds. Saved to readsync_spike_out/", exact, #data.samples, rep.seconds) })
end

function Spike:applyLive()
    if not self.first then return UIManager:show(InfoMessage:new{ text = "Run S8 first" }) end
    local r = self.first
    local item = {
        page = r.pos0, pos0 = r.pos0, pos1 = r.pos1, text = r.text,
        datetime = os.date("%Y-%m-%d %H:%M:%S"),
        drawer = self.ui.highlight.view.highlight.saved_drawer or "lighten",
        note = "readsync spike",
        chapter = self.ui.toc:getTocTitleByPage(r.pos0),
    }
    local idx = self.ui.annotation:addItem(item)
    self.ui:handleEvent(require("ui/event"):new("AnnotationsModified", { item, nb_highlights_added = 1, index_modified = idx }))
    self.ui.rolling:onGotoXPointer(r.pos0)
    UIManager:setDirty("all", "full")
    UIManager:show(InfoMessage:new{ text = "Applied highlight #" .. tostring(idx) .. " and jumped to it. Is it visible without reopening?" })
end

function Spike:removeSpike()
    local a, n = self.ui.annotation.annotations, 0
    for i = #a, 1, -1 do
        if a[i].note == "readsync spike" then
            self.ui.highlight:deleteHighlight(i); n = n + 1
        end
    end
    UIManager:show(InfoMessage:new{ text = "Removed " .. n .. " spike highlight(s)" })
end

-- S10: turn a page every 30 s and hit the network every 20 s, log to a file
function Spike:startS10()
    if self.s10 then return end
    NetworkMgr:runWhenOnline(function()
        self.s10 = { t0 = os.time(), turns = 0, reqs = 0, fails = 0, wifi_lost = 0 }
        local logp = OUT .. "s10_log.txt"
        lfs.mkdir(OUT)
        local function log(m)
            local f = io.open(logp, "a"); if f then f:write(os.date("%H:%M:%S ") .. m .. "\n"); f:close() end
        end
        local bat = require("device"):getPowerDevice()
        log("start battery=" .. tostring(bat:getCapacity()) .. " wifi=" .. tostring(NetworkMgr:isWifiOn()))
        pcall(function() require("device"):setAutoStandby(false) end)
        local function tick_turn()
            if not self.s10 then return end
            self.ui:handleEvent(require("ui/event"):new("GotoViewRel", 1)); self.s10.turns = self.s10.turns + 1
            if os.time() - self.s10.t0 >= 1800 then return self:stopS10() end
            UIManager:scheduleIn(30, tick_turn)
        end
        local function tick_net()
            if not self.s10 then return end
            local socket = require("socket")
            local c = socket.tcp(); c:settimeout(5)
            local ok = c:connect("192.168.1.158", 9092) -- Jadu whisper shim, reachable on LAN
            c:close()
            self.s10.reqs = self.s10.reqs + 1
            if not ok then self.s10.fails = self.s10.fails + 1 end
            if not NetworkMgr:isWifiOn() then self.s10.wifi_lost = self.s10.wifi_lost + 1 end
            if self.s10.reqs % 15 == 0 then log(string.format("t=%ds turns=%d reqs=%d fails=%d wifi_lost=%d battery=%s", os.time() - self.s10.t0, self.s10.turns, self.s10.reqs, self.s10.fails, self.s10.wifi_lost, tostring(bat:getCapacity()))) end
            UIManager:scheduleIn(20, tick_net)
        end
        self.s10.log = log
        UIManager:scheduleIn(30, tick_turn); UIManager:scheduleIn(20, tick_net)
        UIManager:show(InfoMessage:new{ text = "S10 started. 30 min. Leave the Kindle alone.", timeout = 3 })
    end)
end

function Spike:stopS10()
    if not self.s10 then return end
    local s = self.s10; self.s10 = nil
    local bat = require("device"):getPowerDevice()
    local f = io.open(OUT .. "s10_log.txt", "a")
    if f then f:write(string.format("%s end after %ds turns=%d reqs=%d fails=%d wifi_lost=%d battery=%s\n", os.date("%H:%M:%S"), os.time() - s.t0, s.turns, s.reqs, s.fails, s.wifi_lost, tostring(bat:getCapacity()))); f:close() end
    UIManager:show(InfoMessage:new{ text = "S10 stopped" })
end

return Spike
