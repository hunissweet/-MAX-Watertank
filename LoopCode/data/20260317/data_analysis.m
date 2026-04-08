clc;
clear;

% Root data directory
dataDir = '';

% Find all csv files recursively
files = dir(fullfile(dataDir, '**', '*.csv'));

% Preallocate cell arrays
NumFin = {};
TypeFin = {};
MotorAmp = [];
MotorFre = [];
Phase = [];
Flow = [];
Loc_X = [];
Loc_Y = [];
Thrust = [];
Efficiency = [];
FileName = {};

for k = 1:length(files)
    file = files(k);
    fullPath = fullfile(file.folder, file.name);
    [~, baseName, ~] = fileparts(file.name);

    try
        % Parse filename
        % Example:
        % SingL_Jiatype2_Amp30_freq2_phase0_flow0.15_x0_y0_iter1_SingL.csv
        parts = split(baseName, '_');

        % Need at least the main fields
        if numel(parts) < 8
            fprintf('[SKIP] Filename format unexpected: %s\n', file.name);
            continue;
        end

        numFin = char(parts{1});
        typeFin = char(parts{2});
        ampVal = str2double(erase(parts{3}, 'Amp'));
        freVal = str2double(erase(parts{4}, 'freq'));
        phaseVal = str2double(erase(parts{5}, 'phase'));
        flowVal = str2double(erase(parts{6}, 'flow'));
        xVal = str2double(erase(parts{7}, 'x'));
        yVal = str2double(erase(parts{8}, 'y'));

        % Read CSV
        T = readmatrix(fullPath);


        thrustVal = mean(T(:,3), 'omitnan');      % 3rd column
        effVal = mean(T(:,end), 'omitnan');       % last column

        % Store
        NumFin{end+1,1} = numFin;
        TypeFin{end+1,1} = typeFin;
        MotorAmp(end+1,1) = ampVal;
        MotorFre(end+1,1) = freVal;
        Phase(end+1,1) = phaseVal;
        Flow(end+1,1) = flowVal;
        Loc_X(end+1,1) = xVal;
        Loc_Y(end+1,1) = yVal;
        Thrust(end+1,1) = thrustVal;
        Efficiency(end+1,1) = effVal;
        FileName{end+1,1} = file.name;

        fprintf('[OK] %s\n', file.name);

    catch ME
        fprintf('[ERROR] %s\n', file.name);
        fprintf('        %s\n', ME.message);
    end
end

% Make result table
summaryTable = table( ...
    NumFin, TypeFin, MotorAmp, MotorFre, Phase, Flow, Loc_X, Loc_Y, ...
    Thrust, Efficiency, FileName);

disp(summaryTable);

% Save result
writetable(summaryTable, 'summary_results.csv');
fprintf('\nSaved summary to summary_results.csv\n');