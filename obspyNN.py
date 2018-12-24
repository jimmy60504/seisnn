import obspy.io.nordic.core as nordic
from obspy.core import Stream, read
from obspy.core.event.catalog import Catalog
import matplotlib.pyplot as plt


def read_list(sfilelist):
    with open(sfilelist, "r") as file:
        data = []
        while True:
            row = file.readline().split()
            if len(row) == 0:
                break
            data.append(row)
    return data


def load_sfile(sfileList):
    catalog = Catalog()
    for row in sfileList:
        wavename = []
        sfile, wavedir = row[0], row[1]
        sfile_event = nordic.read_nordic(sfile)
        wavename.extend(nordic.readwavename(sfile))
        sfile_event[0].wavename = nordic.readwavename(sfile)
        sfile_event[0].wavedir = wavedir
        catalog += sfile_event
    return catalog


def load_seisan(event):
    stream = Stream()
    wavedir = event.wavedir
    for wave in event.wavename:
        stream += read(wavedir + "/" + str(wave))
    stream.sort(keys=['network', 'station', 'channel'])
    stream.normalize()
    stream.detrend()
    return stream


def load_SDS(event):
    from obspy.clients.filesystem.sds import Client
    sdsRoot = event.wavedir
    t = event.origins[0].time
    stream = Stream()
    client = Client(sds_root=sdsRoot)
    client.nslc = client.get_all_nslc(sds_type="D")
    for net, sta, loc, chan in client.nslc:
        st = client.get_waveforms(net, sta, loc, chan, t, t + 30)
        stream += st
    return stream


def get_picked_stream(event, stream):
    picked_stream = Stream()
    for pick in event.picks:
        station = pick.waveform_id.station_code
        station_stream = stream.select(station=station)
        for trace in station_stream:
            trace.pick = pick
        picked_stream += station_stream
    return picked_stream


def get_probability(stream):
    import scipy.stats as ss
    for trace in stream:
        start_time = trace.meta.starttime
        x_time = trace.times(reftime=start_time)
        pick_time = trace.pick.time - start_time
        sigma = 0.1
        pdf = ss.norm.pdf(x_time, pick_time, sigma)
        trace.pick.pdf = pdf / pdf.max()
    return stream


def split_station_set(stream, station):
    stationset = stream.select(station=station)
    for trace in stationset:
        stream.remove(trace)
    return stream, stationset


def plot_station_set(dataset):
    start_time = dataset[0].stats.starttime
    pick_time = dataset[0].pick.time - start_time
    pick_phase = dataset[0].pick.phase_hint
    subplot = len(dataset) + 1
    fig = plt.figure(figsize=(8, subplot * 2))
    for i in range(len(dataset)):
        ax = fig.add_subplot(subplot, 1, i + 1)
        ax.plot(dataset[i].times(reftime=start_time), dataset[i].data, "k-", label=dataset[i].id)
        y_min, y_max = ax.get_ylim()
        ax.vlines(pick_time, y_min, y_max, color='r', lw=2, label=pick_phase)
        ax.legend()

    ax = fig.add_subplot(subplot, 1, subplot)
    ax.plot(dataset[0].times(reftime=start_time), dataset[0].pick.pdf, "b-", label=pick_phase + " pdf")
    plt.ylim(-0.1, 1.1)
    ax.legend()
    plt.show()


def plot_stream(stream):
    stream.sort(keys=['network', 'station', 'channel'], reverse=True)
    while stream.count():
        station = stream[0].stats.station
        stream, dataset = split_station_set(stream, station)
        plot_station_set(dataset)


def load_dataset(sfileList, plot=False):
    catalog = load_sfile(sfileList)
    dataset = Stream()
    for event in catalog:
        stream = load_SDS(event)
        stream = get_picked_stream(event, stream)
        stream = get_probability(stream)
        dataset += stream
        if plot:
            plot_stream(stream)
    return dataset


def load_training_set(dataset):
    import numpy as np
    wavefile = []
    probability = []
    for trace in dataset:
        wavefile.append(trace.data)
        probability.append(trace.pick.pdf)

    wavefile = np.asarray(wavefile).reshape((len(dataset), 1, 7501, 1))
    probability = np.asarray(probability).reshape((len(dataset), 1, 7501, 1))

    return wavefile, probability


def add_predict(stream, predict):
    i = 0
    for trace in stream:
        trace.pick.pdf = predict[i, :]
        i += 1
    return stream
