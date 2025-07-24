function AutoExportXrkData()
    % Only modify path when not compiled
    if ~isdeployed
        addpath(pwd);
    end

    % Load DLL
    dllPath = fullfile(pwd, 'MatLabXRK-2022-64-ReleaseU.dll');
    protoFile = @AccessAimXrk;

    if ~libisloaded('AccessAimXrk')
        loadlibrary(dllPath, protoFile, 'alias', 'AccessAimXrk');
    end

    % Create data directories
    dataDir = fullfile(pwd, 'data');
    mkdir_if_not_exist(dataDir);

    sortByLapDir = fullfile(dataDir, 'sort_by_lap');
    sortByHeadingDir = fullfile(dataDir, 'sort_by_heading');
    mkdir_if_not_exist(sortByLapDir);
    mkdir_if_not_exist(sortByHeadingDir);

    % Locate XRK file
    files = dir('*.xrk');
    assert(~isempty(files), 'No XRK files found in this directory.');
    sFilename = fullfile(pwd, files(1).name);

    % Open XRK
    iFile = calllib('AccessAimXrk', 'open_file', sFilename);
    assert(iFile > 0, 'Failed to open XRK file.');

    iLapCount = calllib('AccessAimXrk', 'get_laps_count', iFile);
    iChannelCount = calllib('AccessAimXrk', 'get_channels_count', iFile);
    iGpsCount = calllib('AccessAimXrk', 'get_GPS_channels_count', iFile);
    iGpsRawCount = calllib('AccessAimXrk', 'get_GPS_raw_channels_count', iFile);

    % Process all channel types
    export_channels(iFile, iLapCount, iChannelCount, 'channel', ...
        @(f, l, c, t, d, n) calllib(f, 'get_lap_channel_samples', l, c, t, d, n), ...
        @(f, l, c) calllib(f, 'get_lap_channel_samples_count', l, c), ...
        @(f, c) calllib(f, 'get_channel_name_no_spaces', c));

    export_channels(iFile, iLapCount, iGpsCount, 'gps', ...
        @(f, l, c, t, d, n) calllib(f, 'get_lap_GPS_channel_samples', l, c, t, d, n), ...
        @(f, l, c) calllib(f, 'get_lap_GPS_channel_samples_count', l, c), ...
        @(f, c) calllib(f, 'get_GPS_channel_name_no_spaces', c));

    export_channels(iFile, iLapCount, iGpsRawCount, 'rawgps', ...
        @(f, l, c, t, d, n) calllib(f, 'get_lap_GPS_raw_channel_samples', l, c, t, d, n), ...
        @(f, l, c) calllib(f, 'get_lap_GPS_raw_channel_samples_count', l, c), ...
        @(f, c) calllib(f, 'get_GPS_raw_channel_name_no_spaces', c));

    % Close
    calllib('AccessAimXrk', 'close_file_i', iFile);
    unloadlibrary('AccessAimXrk');
    fprintf('✅ All channel data exported to data directory (sort_by_lap and sort_by_heading) for file: %s\n', sFilename);
end

function mkdir_if_not_exist(path)
    if ~exist(path, 'dir')
        mkdir(path);
    end
end

function export_channels(iFile, iLapCount, iChanCount, typeName, getFn, countFn, nameFn)
    baseDir = fullfile(pwd, 'data');
    for iLap = 0:iLapCount-1
        for iChan = 0:iChanCount-1
            chName = nameFn('AccessAimXrk', iChan);
            iSamples = countFn('AccessAimXrk', iFile, iLap, iChan);
            if iSamples <= 0, continue; end

            pTime = libpointer('doublePtr', nan(1, iSamples));
            pData = libpointer('doublePtr', nan(1, iSamples));
            getFn('AccessAimXrk', iFile, iLap, iChan, pTime, pData, iSamples);
            data = [pTime.Value(:), pData.Value(:)];

            filename = sprintf('%s_%s_lap%d.csv', typeName, chName, iLap+1);
            filename = strrep(filename, ' ', '_');

            lapPathLap = fullfile(baseDir, 'sort_by_lap', sprintf('lap_%d', iLap+1), typeName);
            lapPathHead = fullfile(baseDir, 'sort_by_heading', typeName, sprintf('lap_%d', iLap+1));

            mkdir_if_not_exist(lapPathLap);
            mkdir_if_not_exist(lapPathHead);

            writecell([{'Time', chName}; num2cell(data)], fullfile(lapPathLap, filename));
            writecell([{'Time', chName}; num2cell(data)], fullfile(lapPathHead, filename));
        end
    end
end
