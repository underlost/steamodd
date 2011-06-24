"""
Module for reading Steam Economy items

Copyright (c) 2010, Anthony Garcia <lagg@lavabit.com>

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
"""

import json, os, urllib2, time, steam, operator

class Error(Exception):
    def __init__(self, msg):
        Exception.__init__(self)
        self.msg = msg

    def __str__(self):
        return str(self.msg)

class SchemaError(Error):
    def __init__(self, msg, status = 0):
        Error.__init__(self, msg)
        self.msg = msg

class ItemError(Error):
    def __init__(self, msg, item = None):
        Error.__init__(self, msg)
        self.msg = msg
        self.item = item

class schema:
    """ The base class for the item schema. """

    def create_item(self, oitem):
        """ Builds an item using this schema instance and returns it """

        return item(self, oitem)

    def get_language(self):
        """ Returns the ISO code of the language the instance
        is localized to """
        return self._language

    def get_raw_attributes(self, item = None):
        """ Returns all attributes in the schema or for the item if one is given """

        attrs = []
        realattrs = []
        if not item:
            attrs = self._attributes.values()
            attrs.sort(key = operator.itemgetter("defindex"))
            return attrs

        try:
            attrs = self._items[item._item["defindex"]]["attributes"]
        except KeyError: attrs = []

        for specattr in attrs:
            attrid = self._attribute_names[specattr["name"]]
            attrdict = self._attributes[attrid]

            realattrs.append(dict(attrdict.items() + specattr.items()))

        return realattrs

    def get_attributes(self, item = None):
        """ Returns all attributes in the schema
        or the attributes for the item if given"""

        return [item_attribute(attr) for attr in self.get_raw_attributes(item)]

    def get_qualities(self):
        """ Returns a list of all possible item qualities,
        each element will be a dict.
        prettystr is the localized pretty name (e.g. Valve)
        id is the numerical quality (e.g. 8)
        str is the non-pretty string (e.g. developer) """

        return self._qualities

    def _download(self, lang):
        url = ("http://api.steampowered.com/IEconItems_" + self._app_id +
               "/GetSchema/v0001/?key=" + steam.get_api_key() + "&format=json&language=" + lang)
        self._language = lang

        return urllib2.urlopen(url).read()

    def __iter__(self):
        return self.nextitem()

    def nextitem(self):
        iterindex = 0
        iterdata = self._items.values()
        iterdata.sort(key = operator.itemgetter("defindex"))

        while(iterindex < len(iterdata)):
            data = self.create_item(iterdata[iterindex])
            iterindex += 1
            yield data

    def __getitem__(self, key):
        realkey = None
        try: realkey = key["defindex"]
        except: realkey = key

        return self.create_item(self._items[realkey])

    def __init__(self, lang = None):
        """ schema will be used to initialize the schema if given,
        lang can be any ISO language code. """

        schema = None
        if not lang: lang = "en"
        try:
            schema = json.loads(self._download(lang))
        except urllib2.URLError:
            # Try once more
            schema = json.loads(self._download(lang))
        except Exception as E:
            raise SchemaError(E)

        if not schema or schema["result"]["status"] != 1:
            raise SchemaError("Schema error", schema["result"]["status"])

        self._attributes = {}
        self._attribute_names = {}
        for attrib in schema["result"]["attributes"]:
            self._attributes[attrib["defindex"]] = attrib
            self._attribute_names[attrib["name"]] = attrib["defindex"]

        self._items = {}
        for item in schema["result"]["items"]:
            self._items[item["defindex"]] = item

        self._qualities = {}
        for k,v in schema["result"]["qualities"].iteritems():
            aquality = {"id": v, "str": k, "prettystr": k}

            try: aquality["prettystr"] = schema["result"]["qualityNames"][aquality["str"]]
            except KeyError: pass

            self._qualities[v] = aquality

class item:
    """ Stores a single TF2 backpack item """
    # The bitfield in the inventory token where
    # equipped classes are stored
    equipped_field = 0x1FF0000

    # Item image fields in the schema
    ITEM_IMAGE_SMALL = "image_url"
    ITEM_IMAGE_LARGE = "image_url_large"

    def get_attributes(self):
        """ Returns a list of attributes """

        schema_attrs = self._schema.get_raw_attributes(self)
        item_attrs = []
        final_attrs = []

        if self._item != self._schema_item:
            try: item_attrs = self._item["attributes"]
            except KeyError: pass

        usedattrs = []
        for attr in schema_attrs:
            used = False
            for iattr in item_attrs:
                if attr["defindex"] == iattr["defindex"]:
                    final_attrs.append(dict(attr.items() + iattr.items()))
                    used = True
                    usedattrs.append(iattr)
                    break
            if not used:
                final_attrs.append(attr)

        for attr in item_attrs:
            if attr in usedattrs:
                continue
            attrdict = self._schema._attributes[attr["defindex"]]
            final_attrs.append(dict(attrdict.items() + attr.items()))

        return [item_attribute(theattr) for theattr in final_attrs]

    def get_quality(self):
        """ Returns a dict
        prettystr is the localized pretty name (e.g. Valve)
        id is the numerical quality (e.g. 8)
        str is the non-pretty string (e.g. developer) """

        qid = 0
        item = self._item
        qid = item.get("quality", self._schema_item.get("item_quality", 0))
        qualities = self._schema.get_qualities()

        try:
            return qualities[qid]
        except KeyError:
            return {"id": 0, "prettystr": "Broken", "str": "ohnoes"}

    def get_inventory_token(self):
        """ Returns the item's inventory token (a bitfield) """
        return self._item.get("inventory", 0)

    def get_position(self):
        """ Returns a position in the backpack or -1 if there's no position
        available (i.e. an item isn't in the backpack) """

        inventory_token = self.get_inventory_token()

        if inventory_token == 0:
            return -1
        else:
            return inventory_token & 0xFFFF

    def get_equipped_classes(self):
        """ Returns a list of classes (see schema class_bits values) """
        classes = []

        inventory_token = self.get_inventory_token()

        for k,v in self._schema.class_bits.iteritems():
            if ((inventory_token & self.equipped_field) >> 16) & k:
                classes.append(v)

        return classes

    def get_equipable_classes(self):
        """ Returns a list of classes that _can_ use the item. """
        classes = []
        sitem = self._schema_item

        try: classes = sitem["used_by_classes"]
        except KeyError: classes = self._schema.class_bits.values()

        return classes

    def get_schema_id(self):
        """ Returns the item's ID in the schema. """
        return self._item["defindex"]

    def get_name(self):
        """ Returns the item's undecorated name """
        return self._schema_item["item_name"]

    def get_type(self):
        """ Returns the item's type. e.g. "Kukri" for the Tribalman's Shiv.
        If Valve failed to provide a translation the type will be the token without
        the hash prefix. """
        return self._schema_item["item_type_name"]

    def get_image(self, size):
        """ Returns the URL to the item's image, size should be one of
        ITEM_IMAGE_* """
        try:
            return self._schema_item[size]
        except KeyError:
            raise ItemError("Bad item image size given")

    def get_id(self):
        """ Returns the item's unique serial number if it has one """
        return self._item.get("id")

    def get_original_id(self):
        """ Returns the item's original ID if it has one. This is the last "version"
        of the item before it was customized or otherwise changed """
        return self._item.get("original_id")

    def get_level(self):
        """ Returns the item's level (e.g. 10 for The Axtinguisher) if it has one """
        return self._item.get("level")

    def get_slot(self):
        """ Returns the item's slot as a string, this includes "primary",
        "secondary", "melee", and "head" """
        return self._schema_item["item_slot"]

    def get_class(self):
        """ Returns the item's class
        (what you use in the console to equip it, not the craft class)"""
        return self._schema_item.get("item_class")

    def get_craft_class(self):
        """ Returns the item's class in the crafting system if it has one.
        This includes hat, craft_bar, or craft_token. """
        return self._schema_item.get("craft_class")

    def get_custom_name(self):
        """ Returns the item's custom name if it has one. """
        return self._item.get("custom_name")

    def get_custom_description(self):
        """ Returns the item's custom description if it has one. """
        return self._item.get("custom_desc")

    def get_quantity(self):
        """ Returns the number of uses the item has,
        for example, a dueling mini-game has 5 uses by default """
        return self._item.get("quantity", 1)

    def get_description(self):
        """ Returns the item's default description if it has one """
        return self._schema_item.get("item_description")

    def get_min_level(self):
        """ Returns the item's minimum level
        (non-random levels will have the same min and max level) """
        return self._schema_item.get("min_ilevel")

    def get_max_level(self):
        """ Returns the item's maximum level
        (non-random levels will have the same min and max level) """
        return self._schema_item.get("max_ilevel")

    def get_contents(self):
        """ Returns the item in the container, if there is one.
        This will be a standard item object. """
        rawitem = self._item.get("contained_item")
        if rawitem: return self._schema.create_item(rawitem)

    def is_untradable(self):
        """ Returns True if the item cannot be traded, False
        otherwise. """
        # Somewhat a WORKAROUND since this flag is there
        # sometimes, "cannot trade" is there somtimes
        # and then there's "always tradable". Opposed to
        # only occasionally tradable when it feels like it.
        untradable = self._item.get("flag_cannot_trade", False)
        if "cannot trade" in self:
            untradable = True
        return untradable

    def is_name_prefixed(self):
        """ Returns False if the item doesn't use
        a prefix, True otherwise. (e.g. Bonk! Atomic Punch
        shouldn't have a prefix so this would be False) """
        return self._schema_item.get("proper_name", False)

    def get_full_item_name(self, prefixes = {}):
        """
        Generates a prefixed item name and is custom name-aware.

        Will use an alternate prefix dict if given,
        following the format of "non-localized quality": "alternate prefix"

        If you want prefixes stripped entirely call with prefixes = None
        If you want to selectively strip prefixes set the alternate prefix value to
        None in the dict

        """
        quality_str = self.get_quality()["str"]
        pretty_quality_str = self.get_quality()["prettystr"]
        custom_name = self.get_custom_name()
        item_name = self.get_name()
        language = self._schema.get_language()
        prefix = ""

        if item_name.find("The ") != -1 and self.is_name_prefixed():
            item_name = item_name[4:]

        if custom_name:
            item_name = custom_name

        if prefixes != None:
            prefix = prefixes.get(quality_str, pretty_quality_str)

        if prefixes == None or custom_name or (not self.is_name_prefixed() and quality_str == "unique"):
            prefix = ""

        if ((prefixes == None or language != "en") and (quality_str == "unique" or quality_str == "normal")):
            prefix = ""

        if (language != "en" and prefix):
            return item_name + " (" + prefix + ")"

        if prefix: return prefix + " " + item_name
        else: return item_name

    def get_styles(self):
        """ Returns all styles defined for the item """
        styles = self._schema_item.get("styles")

        if not styles: return []

        return [style["name"] for style in styles]

    def get_current_style_id(self):
        """ Returns the style ID of the item if it has one, this is used as an index """
        return self._item.get("style")

    def get_current_style_name(self):
        """ Returns the name of the style if it has one """
        styleid = self.get_current_style_id()
        if styleid:
            try:
                return self.get_styles()[styleid]
            except IndexError:
                return styleid

    def get_capabilities(self):
        """ Returns a list of capabilities, these are flags for what the item can do or be done with """
        caps = self._schema_item.get("capabilities")
        if caps: return [k for k in caps.keys()]
        else: return []

    def get_tool_metadata(self):
        """ Assume this will change. For now returns a dict of various information about tool items """
        return self._schema_item.get("tool")

    def __iter__(self):
        return self.nextattr()

    def nextattr(self):
        iterindex = 0
        attrs = self.get_attributes()

        while(iterindex < len(attrs)):
            data = attrs[iterindex]
            iterindex += 1
            yield data

    def __getitem__(self, key):
        for attr in self:
            if attr.get_id() == key or attr.get_name() == key:
                return attr

        raise KeyError(key)

    def __contains__(self, key):
        try:
            self.__getitem__(key)
            return True
        except KeyError:
            return False

    def __unicode__(self):
        return self.get_full_item_name()

    def __str__(self):
        return unicode(self).encode("utf-8")

    def __init__(self, schema, item):
        self._item = item
        self._schema = schema
        self._schema_item = None

        # Assume it isn't a schema item if it doesn't have a name
        if "item_name" not in self._item:
            try:
                sitem = schema._items[self._item["defindex"]]
                self._schema_item = sitem
            except KeyError:
                pass
        else:
            self._schema_item = item

        if not self._schema_item:
            raise ItemError("Item has no corresponding schema entry")

class item_attribute:
    """ Wrapper around item attributes """

    def get_value_formatted(self, value = None):
        """ Returns a formatted value as a string"""
        if value == None:
            val = self.get_value()
        else:
            val = value
        fattr = str(val)
        ftype = self.get_value_type()

        if ftype == "percentage":
            pval = int(round(val * 100))

            if self.get_type() == "negative":
                pval = 0 - (100 - pval)
            else:
                pval -= 100

            fattr = str(pval)
        elif ftype == "additive_percentage":
            pval = int(round(val * 100))

            fattr = str(pval)
        elif ftype == "inverted_percentage":
            pval = 100 - int(round(val * 100))

            if self.get_type() == "negative":
                if self.get_value_max() > 1:
                    pval = 0 - pval

            fattr = str(pval)
        elif ftype == "additive" or ftype == "particle_index" or ftype == "account_id":
            if int(val) == val: fattr = (str(int(val)))
        elif ftype == "date":
            d = time.gmtime(int(val))
            fattr = time.strftime("%F %H:%M:%S", d)

        return fattr

    def get_description_formatted(self):
        """ Returns a formatted description string (%s* tokens replaced) """
        val = self.get_value()
        ftype = self.get_value_type()
        desc = self.get_description()

        if desc:
            return desc.replace("%s1", self.get_value_formatted())
        else:
            return None

    def get_name(self):
        """ Returns the attributes name """
        return self._attribute["name"]

    def get_class(self):
        return self._attribute["attribute_class"]

    def get_id(self):
        return self._attribute["defindex"]

    def get_value_min(self):
        """ Returns the minimum value for the attribute (not all attributes
        stay above this) """
        return self._attribute["min_value"]

    def get_value_max(self):
        """ Returns the maximum value for the attribute (not all attributes
        stay below this) """
        return self._attribute["max_value"]

    def get_type(self):
        """ Returns the attribute effect type (positive, negative, or neutral) """
        return self._attribute["effect_type"]

    def get_value(self):
        """ Returns the attribute's value, use get_value_type to determine
        the type. """
        return self._attribute.get("value")

    def get_description(self):
        """ Returns the attribute's description string, if
        it is intended to be printed with the value there will
        be a "%s1" token somewhere in the string. Use
        get_description_formatted to substitute this automatically. """
        return self._attribute.get("description_string")

    def get_value_type(self):
        """ Returns the attribute's type. Currently this can be one of
        additive: An integer (convert value to integer) or boolean
        percentage: A standard percentage
        additive_percentage: Could represent a percentage that adds to default stats
        inverted_percentage: The sum of the difference between the value and 100%
        date: A unix timestamp """
        try: return self._attribute["description_format"][9:]
        except KeyError: return None

    def is_hidden(self):
        """ Returns True if the attribute is "hidden"
        (not intended to be shown to the end user). Note
        that hidden attributes also usually have no description string """
        if self._attribute.get("hidden", True) or self.get_description() == None:
            return True
        else:
            return False

    def __unicode__(self):
        """ Pretty printing """
        if not self.is_hidden():
            return self.get_description_formatted()
        else:
            return self.get_name() + ": " + self.get_value_formatted()

    def __str__(self):
        return unicode(self).encode("utf-8")

    def __init__(self, attribute):
        self._attribute = attribute

        # Workaround until Valve gives sane values
        try:
            int(self.get_value())
            # WORKAROUND: There is no type set on this for some reason
            if (self.get_name() == "tradable after date"):
                self._attribute["description_format"] = "value_is_date"
            if (self.get_value_type() != "date" and
                self.get_value() > 1000000000 and
                "float_value" in self._attribute):
                self._attribute["value"] = self._attribute["float_value"]
        except TypeError:
            pass

class backpack:
    """ Functions for reading player inventory """

    def load(self, sid):
        """ Loads or refreshes the player backpack for the given steam.user
        Returns a list of items, will be empty if there's nothing in the backpack"""
        if not isinstance(sid, steam.user.profile):
            sid = steam.user.profile(sid)
        id64 = sid.get_id64()
        url = ("http://api.steampowered.com/IEconItems_" + self._app_id + "/GetPlayerItems/"
               "v0001/?key=" + steam.get_api_key() + "&format=json&SteamID=")
        inv = urllib2.urlopen(url + str(id64)).read()

        # Once again I'm doing what Valve should be doing before they generate
        # JSON. WORKAROUND
        self._inventory_object = json.loads(inv.replace("-1.#QNAN0", "0"))
        result = self._inventory_object["result"]["status"]
        if result == 8:
            raise Error("Bad SteamID64 given")
        elif result == 15:
            raise Error("Profile set to private")
        elif result != 1:
            raise Error("Unknown error")

        itemlist = self._inventory_object["result"]["items"]
        if len(itemlist) and itemlist[0] == None:
            self._inventory_object["result"]["items"] = []

    def get_total_cells(self):
        """ Returns the total number of cells in the backpack.
        This can be used to determine if the user has bought a backpack
        expander. """
        return self._inventory_object["result"].get("num_backpack_slots", 0)

    def set_schema(self, schema):
        """ Sets a new schema to be used on inventory items """
        self._schema = schema

    def __iter__(self):
        return self.nextitem()

    def nextitem(self):
        iterindex = 0
        iterdata = self._inventory_object["result"]["items"]

        while(iterindex < len(iterdata)):
            data = self._schema.create_item(iterdata[iterindex])
            iterindex += 1
            yield data

    def __init__(self, sid = None, oschema = None):
        """ Loads the backpack of user sid if given,
        generates a fresh schema object if one is not given. """

        self._schema = oschema
        if not self._schema:
            self._schema = schema()
        if sid:
            self.load(sid)