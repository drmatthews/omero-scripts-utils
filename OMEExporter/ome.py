#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
from uuid import uuid1 as uuid
from lxml import etree
from tifffile import imsave
from libtiff import TIFF
import numpy as np

class ElementBase():

    def __init__ (self, parent, root):
        self.parent = parent
        self.root = root
        
        n = self.__class__.__name__
        iter_mth = getattr(parent, 'iter_%s' % (n), None)
        if iter_mth is not None:
            for element in iter_mth():
                add_element = getattr(root, 'add_%s' % (n), None)
                add_element(element)
        elif 0:
            print 'NotImplemented: %s.iter_%s(<callable>)' % (parent.__class__.__name__, n)

class TiffImageGenerator:
    
    def __init__(self,conn,source,input_dir,filename,box):
        self.conn = conn
        self.source = source
        self.input_dir = input_dir
        self.filename = filename
        self.box = box
        self.dtype = source.getPixelsType()
        
    def set_tags(self,tif,imageWidth,imageLength,tileWidth,tileHeight):
        tif.SetField('tilewidth',tileWidth)
        tif.SetField('tilelength',tileHeight)
        tif.SetField('imagelength',imageLength)
        tif.SetField('imagewidth',imageWidth)
        tif.SetField('samplesperpixel', 1)
        tif.SetField('orientation',1)
        tif.SetField('photometric', 1)
        tif.SetField('planarconfig', 2)
        bpp = self.bitspersample(self.source.getPixelsType())
        tif.SetField('bitspersample',bpp)
        tif.SetField('compression',5)        
        
    def create_tiles(self,sizeX,sizeY,slicesZ,slicesC,slicesT,description):    

        tileWidth = 1024
        tileHeight = 1024
        primary_pixels = self.source.getPrimaryPixels()
    
        # Make a list of all the tiles we're going to need.
        zctTileList = []
        for z in slicesZ:
            for c in slicesC:
                for t in slicesT:
                    for tileOffsetY in range(
                            0, int((sizeY + tileHeight - 1) / tileHeight)):
                        for tileOffsetX in range(
                                0, int((sizeX + tileWidth - 1) / tileWidth)):
                            x = tileOffsetX * tileWidth
                            y = tileOffsetY * tileHeight
                            w = tileWidth
                            if (w + x > sizeX):
                                w = sizeX - x
                            h = tileHeight
                            if (h + y > sizeY):
                                h = sizeY - y
                            if self.box:
                                tile_xywh = (self.box[0] + x, self.box[1] + y, w, h)
                            else:
                                tile_xywh = (x, y, w, h)
                            zctTileList.append((z, c, t, tile_xywh))
    
        # This is a generator that will return tiles in the sequence above
        # getTiles() only opens 1 rawPixelsStore for all the tiles
        # whereas getTile() opens and closes a rawPixelsStore for each tile.
        tile_gen = primary_pixels.getTiles(zctTileList)
    
        def next_tile():
            return tile_gen.next()
        
        tile_count = 0
        planes = len(slicesZ) * len(slicesC) * len(slicesT)
        tif_image = TIFF.open(os.path.join(self.input_dir,self.filename), 'w')
        for p in range(planes):
            self.set_tags(tif_image,sizeX,sizeY,tileWidth,tileHeight)
            if p == 0:
                tif_image.set_description(description) 

            # tile_image_params sets the key tags per IFD rather than doing so
            # per tile
#                     tif_image.tile_image_params(sizeX,sizeY,1,tileWidth,tileHeight,'lzw')
            
            for tileOffsetY in range(
                    0, ((sizeY + tileHeight - 1) / tileHeight)):
    
                for tileOffsetX in range(
                        0, ((sizeX + tileWidth - 1) / tileWidth)):
    
                    x = tileOffsetX * tileWidth
                    y = tileOffsetY * tileHeight
                    w = tileWidth
    
                    if (w + x > sizeX):
                        w = sizeX - x
    
                    h = tileHeight
                    if (h + y > sizeY):
                        h = sizeY - y
                    
                    tile_count += 1
                    tile_data = next_tile()
                    if (h != tile_data.shape[0]) or (w != tile_data.shape[1]):
                        h = tile_data.shape[0]
                        w = tile_data.shape[1]
                    tile_dtype = tile_data.dtype
                    tile = np.zeros((1,tileWidth,tileHeight),dtype=tile_dtype)
                    tile[0,:h,:w] = tile_data[:,:]                     
                    tif_image.write_tile(tile,x,y)
            tif_image.WriteDirectory()
        tif_image.close()
        return tile_count
        
    def create_planes(self,sizeX,sizeY,slicesZ,slicesC,slicesT,description):
        sizeZ = len(slicesZ)
        sizeC = len(slicesC)
        sizeT = len(slicesT)
        if self.box:
            roi = self.box[:-1]
            zctList = []
            for z in slicesZ:
                for c in slicesC:
                    for t in slicesT:
                        zctList.append((z,c,t,roi))
                        
            planes = self.source.getPrimaryPixels().getTiles(zctList)    # A generator (not all planes in hand)
        else:
            zctList = []
            for z in slicesZ:
                for c in slicesC:
                    for t in slicesT:
                        zctList.append((z,c,t))
                        
            planes = self.source.getPrimaryPixels().getPlanes(zctList)    # A generator (not all planes in hand) 
        plane_list = []
        for i,p in enumerate(planes):
            plane_list.append(p)
    
        p = 0
        image_data = np.zeros((sizeZ,sizeC,sizeT,sizeY,sizeX),dtype=self.dtype)
        for z in range(sizeZ):
            for c in range(sizeC):
                for t in range(sizeT):
                    image_data[z,c,t,:,:] = plane_list[p]
                    p += 1

        imsave(os.path.join(self.input_dir,self.filename),image_data,description=description,compress=6)
        
    @staticmethod
    def bitspersample(dtype):
        return dict(uint8=8,uint16=16).get(dtype)
        

class Dataset(ElementBase): pass            
class Group(ElementBase): pass
class Experimenter(ElementBase): pass
class Instrument(ElementBase): pass
class Image(ElementBase): pass
class ROI(ElementBase): pass

class OMEBase:
    """ Base class for OME-XML writers.
    """

#     _subelement_classes = [Dataset, Experimenter, Group, Instrument, Image]
    _subelement_classes = [Image, ROI]

    prefix = ''
    def __init__(self):
        self.tif_images = {}

    def generate(self, options=None, validate=False):
        template_xml = self.make_xml()
        tif_gen = TiffImageGenerator(self.conn,self.source,self.input_dir,self.filename,self.box)
        self.tif_images[self.tif_filename,self.tif_uuid,self.PhysSize] = tif_gen

        s = None
        for (fn, uuid, res), tif_gen in self.tif_images.items():
                
            if s is None and validate:
                s = etree.tostring(template_xml.to_etree(), encoding='UTF-8', xml_declaration=True)
            else:
                s = etree.tostring(template_xml.to_etree(), encoding='UTF-8', xml_declaration=True)
            if (self.sizeX < 4096) and (self.sizeY < 4096):
                tif_gen.create_planes(self.sizeX,self.sizeY,self.slicesZ,self.slicesC,self.slicesT,s)
            else:
                tc = tif_gen.create_tiles(self.sizeX,self.sizeY,self.slicesZ,self.slicesC,self.slicesT,s)
            print 'SUCCESS!'

        return s

    def _mk_uuid(self):
        return 'urn:uuid:%s' % (uuid())

    def make_xml(self):
        self.temp_uuid = self._mk_uuid()
        xml = self.store
        xml.set_UUID(self.temp_uuid)
        for element_cls in self._subelement_classes:
            if element_cls.__name__ == "ROI":
                nsn = "roi"
            else:
                nsn = "ome"
            element_cls(self, xml) # element_cls should append elements to root
        return xml   

    def get_AcquiredDate(self):
        return None

    @staticmethod
    def dtype2PixelIType(dtype):
        return dict (int8='int8',int16='int16',int32='int32',
                     uint8='uint8',uint16='uint16',uint32='uint32',
                     complex128='double-complex', complex64='complex',
                     float64='double', float32='float',
                     ).get(dtype.name, dtype.name)