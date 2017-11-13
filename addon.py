# -*- coding:utf-8-*-
#
#      Copyright (C) 2017 Yllar Pajus
#      http://pilves.eu
#
#  This Program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2, or (at your option)
#  any later version.
#
#  This Program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this Program; see the file LICENSE.txt.  If not, write to
#  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
#  http://www.gnu.org/copyleft/gpl.html
#
import os
import sys
import urlparse
import urllib2
import re
import json
from bs4 import BeautifulSoup

import xbmc
import xbmcgui
import xbmcaddon
import xbmcplugin

import buggalo

__settings__ = xbmcaddon.Addon(id='plugin.video.kanal2.ee')


class Kanal2Exception(Exception):
    pass


class Kanal2Addon(object):
    def download_url(self, url, xreq=None):
        for retries in range(0, 5):
            try:
                r = urllib2.Request(url.encode('iso-8859-1', 'replace'))
                r.add_header('User-Agent',
                             'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:10.0.2) Gecko/20100101 Firefox/10.0.2')
                if xreq:
                    r.add_header('X-Requested-With', 'XMLHttpRequest')
                u = urllib2.urlopen(r, timeout=30)
                contents = u.read()
                u.close()
                return contents
            except Exception, ex:
                if retries >= 4:
                    raise Kanal2Exception(ex)

    # list all the shows
    def list_programs(self):
        url = "http://kanal2.postimees.ee/pluss/shows?tab=arhiiv"
        buggalo.addExtraData('url', url)
        html = self.download_url(url)

        saated = {}
        for m in re.finditer('local:(.*)', html):
            saated = m.group(1).replace('tokens:', '\"tokens\":')
        saated = saated[:-1]  # remove trailing comma
        saated = saated.replace("\\'", "'")  # replace invalid escapes
        saated = json.loads(saated)  # load as JSON

        items = list()
        for s in sorted(saated):
            # set fetch to None so it would not fetch all the pictures at once
            fanart = self.download_and_cache_fanart(s['url'], None)
            item = xbmcgui.ListItem(s['name'], iconImage=fanart)
            item.setProperty('Fanart_Image', fanart)
            items.append((PATH + '?program=%s' % s['url'], item, True))
        xbmcplugin.addDirectoryItems(HANDLE, items)
        xbmcplugin.endOfDirectory(HANDLE)

    # list all episodes
    def list_videos(self, saade):
        url = "https://kanal2.postimees.ee/pluss/saade/%s?onpage=36" % saade
        xbmc.log('saate url: %s' % url, xbmc.LOGNOTICE)
        fanart = self.download_and_cache_fanart(saade, True)  # download pictures
        buggalo.addExtraData('url', url)
        html = BeautifulSoup(self.download_url(url), 'html.parser')
        if not html:
            raise Kanal2Exception(ADDON.getLocalizedString(203))

        try:
            blocks = html.find_all(class_="row onevideo_2col")
        except Exception, ex:
            raise Kanal2Exception(str(ex))
        items = list()
        for block in blocks:
            title = "%s %s " % (block.find(class_="videometa").a.get_text().strip(),
                                block.find(class_="videometa").small.get_text().strip())
            # rating = int(node.findtext('rating/value')) * 2.0
            rating = int(3.4563) * 2.0
            date = block.find(class_="videometa").span.get_text().strip().replace('EETRIS ', '')
            infoLabels = {
                'rating': rating,
                'date': date,
                'title': title
            }
            # print "Pilt: " + node.findtext('thumbUrl')
            url = "https://kanal2.postimees.ee%s" % block.find(class_="videometa").a.get('href')
            if url:  # get IDs
                idsplit = re.search('.*=([^$]+)', url, re.DOTALL)
                # print "ID: http://kanal2.ee/video/playerPlaylistApi?id=%s" %  idsplit.group(1)
                item = xbmcgui.ListItem(title, iconImage=fanart)
                item.setInfo('video', infoLabels)
                item.setProperty('IsPlayable', 'true')
                item.setProperty('Fanart_Image', fanart)
                items.append((PATH + '?show=%s' % idsplit.group(1), item))
        xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_DATE)
        xbmcplugin.addDirectoryItems(HANDLE, items)
        xbmcplugin.endOfDirectory(HANDLE)

    def get_video_url(self, videoid):
        """Get actual video file and start playing."""
        url = 'https://kanal2.postimees.ee/pluss/video/?id=%s' % videoid
        buggalo.addExtraData('url', url)
        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        playlist.clear()

        html = self.download_url(url)
        if not html:
            raise Kanal2Exception(ADDON.getLocalizedString(203))

        init = re.search("initK2Player.*\', \'episodes\', \'%s\', \'([^\']+)\'\);" % videoid, html, re.DOTALL)
        try:
            if init.group(1):
                dataurl = self.download_url("http://kanal2.postimees.ee/player/playlist/%s?type=episodes" % videoid,
                                            True)
                data = json.loads(dataurl)
                if not data:
                    raise Kanal2Exception(ADDON.getLocalizedString(202))

                videoUrl = "https://kanal-vod.babahhcdn.com/bb1037/_definst_/smil:kanal2/%s/playlist.m3u8?t=%s" % (
                data['data']['file'], init.group(1))
                infoLabels = {
                    'title': data['info']['subtitle'],
                    'plot': data['info']['description']
                }
                item = xbmcgui.ListItem(data['info']['subtitle'], iconImage=ICON, path=videoUrl)
                item.setInfo('video', infoLabels)
                playlist.add(videoUrl, item)
        except AttributeError:
            raise Kanal2Exception(ADDON.getLocalizedString(204))
        # start = 0
        xbmcplugin.setResolvedUrl(HANDLE, True, item)

    def download_and_cache_fanart(self, saade, fetch):
        url = 'http://kanal2.postimees.ee/saated/%s' % saade
        fanartPath = os.path.join(CACHE_PATH, '%s.jpg' % saade.encode('iso-8859-1', 'replace'))
        fanartUrl = None

        if fetch is None:
            html = None
        else:
            html = self.download_url(url)

        if not os.path.exists(fanartPath) and html:
            m = re.search('image saated" style="background-image: url\(([^)+]+)', html)
            if m:
                fanartUrl = "http://kanal2.postimees.ee/" + m.group(1)

            if fanartUrl:
                imageData = self.download_url(fanartUrl.replace(' ', '%20'))
                if imageData:
                    f = open(fanartPath, 'wb')
                    f.write(imageData)
                    f.close()

                    return fanartPath

        elif os.path.exists(fanartPath):
            return fanartPath

        return FANART

    def display_error(self, message='n/a'):
        heading = buggalo.getRandomHeading()
        line1 = ADDON.getLocalizedString(200)
        line2 = ADDON.getLocalizedString(201)
        xbmcgui.Dialog().ok(heading, line1, line2, message)


if __name__ == '__main__':
    ADDON = xbmcaddon.Addon()
    PATH = sys.argv[0]
    HANDLE = int(sys.argv[1])
    PARAMS = urlparse.parse_qs(sys.argv[2][1:])

    ICON = os.path.join(ADDON.getAddonInfo('path'), 'icon.png')
    FANART = os.path.join(ADDON.getAddonInfo('path'), 'fanart.jpg')

    CACHE_PATH = xbmc.translatePath(ADDON.getAddonInfo("Profile"))
    if not os.path.exists(CACHE_PATH):
        os.makedirs(CACHE_PATH)

    buggalo.SUBMIT_URL = 'https://pilves.eu/exception/submit.php'
    kanal2Addon = Kanal2Addon()
    try:
        if PARAMS.has_key('program'):
            kanal2Addon.list_videos(PARAMS['program'][0])
        elif PARAMS.has_key('show'):
            kanal2Addon.get_video_url(PARAMS['show'][0])
        else:
            kanal2Addon.list_programs()
    except Kanal2Exception, ex:
        kanal2Addon.display_error(str(ex))
    except Exception:
        buggalo.onExceptionRaised()
